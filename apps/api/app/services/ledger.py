"""The only module allowed to write financial_transactions / journal_lines."""
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..errors import Conflict, Invalid, NotFound
from ..models import Account, FinancialTransaction, JournalLine, Reconciliation
from ..money import parse_money
from .accounts import balance

BASE_CURRENCY = "EUR"


@dataclass
class Line:
    account_id: object
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")


def _hash(type_, occurred_at, lines, expense_id) -> str:
    norm = sorted((str(l.account_id), str(l.debit), str(l.credit)) for l in lines)
    return hashlib.sha256(json.dumps([type_, str(occurred_at), norm, str(expense_id)]).encode()).hexdigest()


def period_is_closed(db: Session, user_id, day: date) -> bool:
    r = db.scalar(select(Reconciliation).where(
        Reconciliation.user_id == user_id, Reconciliation.year == day.year, Reconciliation.month == day.month,
        Reconciliation.status == "closed"))
    return r is not None


def _check_open_periods(db, accounts: list[Account], day: date):
    for a in accounts:
        if a.kind == "employee_wallet" and a.owner_user_id and period_is_closed(db, a.owner_user_id, day):
            raise Conflict(
                f"Period {day.year}-{day.month:02d} is closed for this employee; reopen it first",
                code="period_closed")


def post_transaction(
    db: Session, *, household_id, type: str, lines: list[Line], key: str, occurred_at: date,
    description: str = "", created_by=None, expense_id=None, reverses_id=None, currency: str = BASE_CURRENCY,
    reason: str | None = None,
) -> tuple[FinancialTransaction, bool]:
    """Post a balanced, idempotent transaction. Returns (txn, replayed)."""
    if currency != BASE_CURRENCY:
        raise Invalid("Only EUR is supported in Phase 1", code="currency_unsupported")
    if not key or len(key) > 200:
        raise Invalid("idempotency key required", code="idempotency_key_required")
    if len(lines) < 2:
        raise Invalid("Transaction needs at least two lines", code="too_few_lines")
    for l in lines:
        l.debit = parse_money(l.debit, positive=False, field="debit")
        l.credit = parse_money(l.credit, positive=False, field="credit")
        if (l.debit > 0) == (l.credit > 0):
            raise Invalid("Each line must have exactly one positive side", code="bad_line")
    if sum(l.debit for l in lines) != sum(l.credit for l in lines):
        raise Invalid("Unbalanced transaction", code="unbalanced")

    phash = _hash(type, occurred_at, lines, expense_id)

    def existing():
        return db.scalar(select(FinancialTransaction).where(
            FinancialTransaction.household_id == household_id, FinancialTransaction.idempotency_key == key))

    def resolve(ex):
        if ex.payload_hash != phash:
            raise Conflict("Idempotency key reused with a different payload", code="idempotency_conflict")
        return ex, True

    ex = existing()
    if ex:
        return resolve(ex)

    ids = sorted({l.account_id for l in lines}, key=str)
    accs = db.scalars(select(Account).where(Account.id.in_(ids)).order_by(Account.id).with_for_update()).all()
    if len(accs) != len(ids) or any(a.household_id != household_id for a in accs):
        raise NotFound("Account not found", code="account_not_found")
    if any(not a.is_active for a in accs):
        raise Invalid("Account inactive", code="account_inactive")
    amap = {a.id: a for a in accs}
    _check_open_periods(db, accs, occurred_at)

    # rows are locked; re-check idempotency now that we serialise on the accounts
    ex = existing()
    if ex:
        return resolve(ex)

    txn = FinancialTransaction(
        household_id=household_id, type=type, description=description[:500], occurred_at=occurred_at,
        currency=currency, idempotency_key=key, payload_hash=phash, expense_id=expense_id,
        reverses_id=reverses_id, created_by=created_by, reason=reason,
        created_at=datetime.now(timezone.utc))
    try:
        with db.begin_nested():
            db.add(txn)
            db.flush()
    except IntegrityError:
        ex = existing()
        if ex:
            return resolve(ex)
        raise
    for l in lines:
        db.add(JournalLine(
            transaction_id=txn.id, account_id=l.account_id, debit=l.debit, credit=l.credit, currency=currency,
            fx_rate=Decimal("1"), base_debit=l.debit, base_credit=l.credit))
    db.flush()

    # assets (bank, wallets) can never go negative
    for aid in ids:
        a = amap[aid]
        if a.type == "asset" and any(l.account_id == aid and l.credit > 0 for l in lines):
            if balance(db, aid) < 0:
                raise Conflict(f"Insufficient funds in '{a.name}'", code="insufficient_funds", account_id=str(aid))
    db.refresh(txn)
    return txn, False


def reverse_transaction(db: Session, txn_id, *, household_id, reason: str, actor_id, occurred_at: date | None = None):
    orig = db.scalar(select(FinancialTransaction).where(FinancialTransaction.id == txn_id).with_for_update())
    if not orig or orig.household_id != household_id:
        raise NotFound("Transaction not found")
    if orig.reverses_id:
        raise Conflict("A reversal cannot be reversed", code="cannot_reverse_reversal")
    if orig.status == "reversed":
        raise Conflict("Already reversed", code="already_reversed")
    if not reason or not reason.strip():
        raise Invalid("Reason required", code="reason_required")
    lines = [Line(account_id=l.account_id, debit=l.credit, credit=l.debit) for l in orig.lines]
    rev, replayed = post_transaction(
        db, household_id=household_id, type=orig.type, lines=lines, key=f"reverse:{orig.id}",
        occurred_at=occurred_at or date.today(), description=f"Anulim: {orig.description}"[:500],
        created_by=actor_id, expense_id=orig.expense_id, reverses_id=orig.id, reason=reason.strip())
    if not replayed:
        orig.status = "reversed"
        orig.reversed_by_id = rev.id
        db.flush()
    return rev
