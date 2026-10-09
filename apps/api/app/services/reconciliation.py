from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import Conflict, Forbidden, Invalid, NotFound
from ..models import (
    Document, Expense, FinancialTransaction, JournalLine, Reconciliation, ReconciliationEvent, User,
)
from ..money import fmt, parse_money
from ..rbac import ADMIN_ROLES
from . import accounts as acc
from .audit import audit
from .ledger import Line, post_transaction, reverse_transaction

IN_BUCKETS = {
    "atm_withdrawal": "withdrawals", "employee_transfer": "transfers_in", "refund": "refunds",
}
OUT_BUCKETS = {
    "cash_expense": "cash_expenses", "cash_return": "returns_to_bank", "employee_transfer": "transfers_out",
}


def month_bounds(year: int, month: int):
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _record(db, hh, user_id, year, month, create=False) -> Reconciliation | None:
    r = db.scalar(select(Reconciliation).where(
        Reconciliation.user_id == user_id, Reconciliation.year == year, Reconciliation.month == month))
    if not r and create:
        r = Reconciliation(household_id=hh, user_id=user_id, year=year, month=month)
        db.add(r)
        db.flush()
    return r


def compute(db: Session, hh, user_id, year: int, month: int) -> dict:
    u = db.get(User, user_id)
    if not u or u.household_id != hh:
        raise NotFound("User not found")
    start, end = month_bounds(year, month)
    wallet = acc.wallet_for(db, hh, user_id)
    opening = acc.balance(db, wallet.id, before=start)
    rows = db.execute(
        select(JournalLine, FinancialTransaction).join(FinancialTransaction, FinancialTransaction.id == JournalLine.transaction_id)
        .where(JournalLine.account_id == wallet.id, FinancialTransaction.occurred_at >= start,
               FinancialTransaction.occurred_at <= end)).all()
    b = {k: Decimal(0) for k in ("withdrawals", "transfers_in", "other_sources", "refunds", "cash_expenses",
                                 "returns_to_bank", "transfers_out", "other_outflows", "count_adjustment")}
    for line, txn in rows:
        is_in = line.debit > 0
        amt = line.debit if is_in else line.credit
        sign = 1
        if txn.reverses_id:  # a reversal nets against the original bucket
            is_in, sign = not is_in, -1
        if txn.type == "cash_difference":
            b["count_adjustment"] += sign * amt * (1 if is_in else -1)
            continue
        if is_in:
            b[IN_BUCKETS.get(txn.type, "other_sources")] += sign * amt
        else:
            b[OUT_BUCKETS.get(txn.type, "other_outflows")] += sign * amt
    inflow = b["withdrawals"] + b["transfers_in"] + b["other_sources"] + b["refunds"]
    outflow = b["cash_expenses"] + b["returns_to_bank"] + b["transfers_out"] + b["other_outflows"]
    expected = opening + inflow - outflow
    ledger_close = acc.balance(db, wallet.id, upto=end)

    def sum_status(statuses, cash_only=False):
        q = select(func.coalesce(func.sum(Expense.total), 0), func.count()).where(
            Expense.user_id == user_id, Expense.status.in_(statuses), Expense.is_refund.is_(False),
            Expense.expense_date >= start, Expense.expense_date <= end)
        if cash_only:
            q = q.where(Expense.payment_method == "cash")
        s, c = db.execute(q).one()
        return {"amount": fmt(Decimal(s)), "count": c}

    missing = db.scalar(select(func.count()).select_from(Expense).where(
        Expense.user_id == user_id, Expense.is_refund.is_(False), Expense.expense_date >= start,
        Expense.expense_date <= end, Expense.status.in_(("submitted", "approved", "posted")),
        ~select(Document.id).where(Document.expense_id == Expense.id).exists()))
    suspense = acc.balance(db, acc.system_account(db, hh, "suspense").id)
    rec = _record(db, hh, user_id, year, month)
    declared = rec.declared_count if rec else None
    return {
        "user_id": str(user_id), "user_name": u.name, "year": year, "month": month,
        "status": rec.status if rec else "open",
        "opening": fmt(opening), "withdrawals": fmt(b["withdrawals"]), "transfers_in": fmt(b["transfers_in"]),
        "other_sources": fmt(b["other_sources"]), "refunds": fmt(b["refunds"]),
        "cash_expenses": fmt(b["cash_expenses"]), "returns_to_bank": fmt(b["returns_to_bank"]),
        "transfers_out": fmt(b["transfers_out"]), "other_outflows": fmt(b["other_outflows"]),
        "expected_closing": fmt(expected), "count_adjustment": fmt(b["count_adjustment"]),
        "ledger_closing": fmt(ledger_close), "consistent": ledger_close == expected + b["count_adjustment"],
        "declared_count": fmt(declared), "difference": fmt(declared - expected) if declared is not None else None,
        "pending": sum_status(("draft", "uploaded", "processing", "needs_review", "submitted")),
        "approved_not_posted": sum_status(("approved",)),
        "rejected": sum_status(("rejected",)),
        "posted_cash": sum_status(("posted",), cash_only=True),
        "missing_receipts": missing,
        "suspense_balance": fmt(suspense),
        "difference_txn_id": str(rec.difference_txn_id) if rec and rec.difference_txn_id else None,
        "note": rec.note if rec else None,
    }


def _check_period(year, month):
    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        raise Invalid("Bad period", code="bad_period")
    if date(year, month, 1) > date.today():
        raise Invalid("Period is in the future", code="future_period")


def declare(db: Session, auth, user_id, year, month, amount):
    _check_period(year, month)
    if user_id != auth.user.id and auth.user.role not in ADMIN_ROLES:
        raise NotFound("Not found")
    u = db.get(User, user_id)
    if not u or u.household_id != auth.hh or u.role != "employee":
        raise NotFound("Employee not found")
    amt = parse_money(amount, positive=False, field="declared_count")
    if amt < 0:
        raise Invalid("Count cannot be negative", code="amount_negative")
    r = _record(db, auth.hh, user_id, year, month, create=True)
    if r.status == "closed":
        raise Conflict("Period is closed", code="period_closed")
    r.declared_count = amt
    db.add(ReconciliationEvent(reconciliation_id=r.id, action="declare", actor_id=auth.user.id))
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="reconciliation.declare", entity_type="reconciliation",
          entity_id=r.id, details={"declared": str(amt), "period": f"{year}-{month:02d}"})
    return r


def close(db: Session, auth, user_id, year, month, post_difference: bool, note: str | None):
    if auth.user.role not in ADMIN_ROLES:
        raise Forbidden("Only financial admins can close periods")
    _check_period(year, month)
    r = _record(db, auth.hh, user_id, year, month, create=True)
    r = db.scalar(select(Reconciliation).where(Reconciliation.id == r.id).with_for_update())
    if r.status == "closed":
        raise Conflict("Already closed", code="period_closed")
    if r.declared_count is None:
        raise Invalid("The employee must declare the physical cash count first", code="count_missing")
    c = compute(db, auth.hh, user_id, year, month)
    expected = Decimal(c["expected_closing"])
    diff = r.declared_count - expected
    if diff != 0 and not post_difference and not (note and note.strip()):
        raise Invalid("A note is required when leaving a difference unposted", code="note_required")
    n_closes = db.scalar(select(func.count()).select_from(ReconciliationEvent).where(
        ReconciliationEvent.reconciliation_id == r.id, ReconciliationEvent.action == "close"))
    if diff != 0 and post_difference:
        wallet = acc.wallet_for(db, auth.hh, user_id)
        susp = acc.system_account(db, auth.hh, "suspense")
        _, end = month_bounds(year, month)
        lines = ([Line(susp.id, debit=-diff), Line(wallet.id, credit=-diff)] if diff < 0
                 else [Line(wallet.id, debit=diff), Line(susp.id, credit=diff)])
        txn, _ = post_transaction(db, household_id=auth.hh, type="cash_difference", lines=lines,
                                  key=f"recon-diff:{r.id}:{n_closes}", occurred_at=end,
                                  description="Diference gjate pajtimit", created_by=auth.user.id)
        r.difference_txn_id = txn.id
    r.expected_closing, r.difference, r.note = expected, diff, (note or None)
    r.status, r.closed_by, r.closed_at = "closed", auth.user.id, datetime.now(timezone.utc)
    db.add(ReconciliationEvent(reconciliation_id=r.id, action="close", actor_id=auth.user.id, reason=note))
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="reconciliation.close", entity_type="reconciliation",
          entity_id=r.id, details={"period": f"{year}-{month:02d}", "difference": str(diff), "posted": bool(r.difference_txn_id)})
    return r


def reopen(db: Session, auth, user_id, year, month, reason: str):
    if auth.user.role not in ADMIN_ROLES:
        raise Forbidden("Only financial admins can reopen periods")
    if not reason or not reason.strip():
        raise Invalid("Reason required", code="reason_required")
    r = _record(db, auth.hh, user_id, year, month)
    if not r:
        raise NotFound("Reconciliation not found")
    r = db.scalar(select(Reconciliation).where(Reconciliation.id == r.id).with_for_update())
    if r.status != "closed":
        raise Conflict("Period is not closed", code="not_closed")
    r.status = "open"
    db.flush()
    if r.difference_txn_id:
        orig = db.get(FinancialTransaction, r.difference_txn_id)
        if orig.status != "reversed":
            reverse_transaction(db, orig.id, household_id=auth.hh, reason=f"reopen: {reason}", actor_id=auth.user.id,
                                occurred_at=orig.occurred_at)
        r.difference_txn_id = None
    db.add(ReconciliationEvent(reconciliation_id=r.id, action="reopen", actor_id=auth.user.id, reason=reason.strip()))
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="reconciliation.reopen", entity_type="reconciliation",
          entity_id=r.id, details={"period": f"{year}-{month:02d}", "reason": reason.strip()[:200]})
    return r
