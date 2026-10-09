import re
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import Conflict, Forbidden, Invalid, NotFound
from ..models import (
    Category, Document, Expense, ExpenseStatusHistory, OcrCorrection, OcrResult, Supplier, User,
)
from ..money import parse_money
from ..rbac import ADMIN_ROLES
from . import accounts as acc
from .audit import audit
from .ledger import Line, post_transaction, reverse_transaction

TRANSITIONS: dict[str, set[str]] = {
    "draft": {"uploaded", "submitted"},
    "uploaded": {"processing", "needs_review", "submitted"},
    "processing": {"needs_review"},
    "needs_review": {"submitted"},
    "submitted": {"approved", "rejected", "needs_review"},
    "approved": {"posted", "rejected"},
    "rejected": {"draft"},
    "posted": {"reversed"},
    "reversed": set(),
}
EDITABLE = {"draft", "uploaded", "processing", "needs_review"}
PAYMENT_METHODS = {"cash", "card", "bank_transfer", "personal_funds"}
PENDING = ("draft", "uploaded", "processing", "needs_review", "submitted")


def norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def transition(db: Session, e: Expense, to: str, actor_id, note: str | None = None):
    if to not in TRANSITIONS.get(e.status, set()):
        raise Conflict(f"Invalid transition {e.status} -> {to}", code="invalid_transition")
    db.add(ExpenseStatusHistory(expense_id=e.id, from_status=e.status, to_status=to, actor_id=actor_id, note=note))
    e.status = to
    e.updated_at = datetime.now(timezone.utc)


def get_expense(db: Session, auth, expense_id, *, for_update=False) -> Expense:
    q = select(Expense).where(Expense.id == expense_id, Expense.household_id == auth.hh)
    if for_update:
        q = q.with_for_update()
    e = db.scalar(q)
    if not e:
        raise NotFound("Expense not found")
    if auth.user.role == "employee" and e.user_id != auth.user.id:
        raise NotFound("Expense not found")  # object-level ownership; do not leak existence
    return e


def _supplier(db, hh, name):
    if not name or not name.strip():
        return None
    n = norm_name(name)
    s = db.scalar(select(Supplier).where(Supplier.household_id == hh, Supplier.normalized_name == n))
    if not s:
        s = Supplier(household_id=hh, name=name.strip(), normalized_name=n)
        db.add(s)
        db.flush()
    return s


def _validate_fields(db, auth, e: Expense, data: dict):
    hh = auth.hh
    if "category_id" in data and data["category_id"]:
        c = db.get(Category, data["category_id"])
        if not c or c.household_id != hh or not c.is_active:
            raise Invalid("Category not found", code="category_not_found")
    if "payment_method" in data and data["payment_method"] not in PAYMENT_METHODS:
        raise Invalid("Invalid payment method", code="bad_payment_method")
    if data.get("expense_date") and data["expense_date"] > date.today():
        raise Invalid("Date cannot be in the future", code="future_date")


def _latest_extraction(db, expense_id):
    rows = db.scalars(select(OcrResult).where(OcrResult.expense_id == expense_id, OcrResult.status == "done")
                      .order_by(OcrResult.created_at)).all()
    merged: dict = {}
    for r in rows:
        for k in ("supplier", "date", "total"):
            v = (r.extraction or {}).get(k, {}).get("value")
            if v is not None and k not in merged:
                merged[k] = v
    return merged


def apply_fields(db: Session, auth, e: Expense, data: dict):
    _validate_fields(db, auth, e, data)
    ext = _latest_extraction(db, e.id) if e.documents else {}
    pairs = {"supplier_name": ("supplier", lambda v: v), "expense_date": ("date", lambda v: str(v)),
             "total": ("total", lambda v: str(v))}
    for f in ("category_id", "supplier_name", "expense_date", "total", "payment_method", "notes", "bank_account_id"):
        if f not in data:
            continue
        v = data[f]
        if f == "total" and v is not None:
            v = parse_money(v, field="total")
        if f == "bank_account_id" and v:
            acc.get_bank(db, auth.hh, v)
        if f in pairs and f in data and ext.get(pairs[f][0]) is not None:
            oldv = str(ext[pairs[f][0]])
            newv = None if v is None else pairs[f][1](v)
            if newv != oldv:
                db.add(OcrCorrection(expense_id=e.id, field=f, old_value=oldv, new_value=newv, user_id=auth.user.id))
        setattr(e, f, v)
        if f == "supplier_name":
            e.supplier_id = _supplier(db, auth.hh, v).id if v else None
    e.updated_at = datetime.now(timezone.utc)


def create_expense(db: Session, auth, data: dict) -> tuple[Expense, bool]:
    owner_id = data.get("user_id") or auth.user.id
    if owner_id != auth.user.id and auth.user.role not in ADMIN_ROLES:
        raise Forbidden("Cannot create expenses for others")
    owner = db.get(User, owner_id)
    if not owner or owner.household_id != auth.hh:
        raise NotFound("User not found")
    if data.get("payment_method") and data["payment_method"] not in PAYMENT_METHODS:
        raise Invalid("Invalid payment method", code="bad_payment_method")
    ref = data.get("client_ref")
    if ref:
        ex = db.scalar(select(Expense).where(Expense.user_id == owner_id, Expense.client_ref == ref))
        if ex:
            return ex, True
    e = Expense(household_id=auth.hh, user_id=owner_id, created_by=auth.user.id, client_ref=ref,
                payment_method=data.get("payment_method") or "cash", status="draft")
    db.add(e)
    db.flush()
    db.add(ExpenseStatusHistory(expense_id=e.id, from_status=None, to_status="draft", actor_id=auth.user.id))
    fields = {k: v for k, v in data.items() if k in ("category_id", "supplier_name", "expense_date", "total", "notes", "bank_account_id") and v not in (None, "")}
    if fields:
        apply_fields(db, auth, e, fields)
    if e.payment_method in ("card", "bank_transfer") and not e.bank_account_id:
        b = acc.default_bank(db, auth.hh)
        e.bank_account_id = b.id if b else None
    db.flush()
    return e, False


def update_expense(db: Session, auth, e: Expense, data: dict):
    if e.status not in EDITABLE:
        raise Conflict("Expense can no longer be edited", code="not_editable")
    apply_fields(db, auth, e, data)


def submit(db: Session, auth, e: Expense, confirm_low_confidence: bool = False):
    if e.status not in ("draft", "uploaded", "needs_review"):
        raise Conflict(f"Cannot submit from {e.status}", code="invalid_transition")
    missing = [f for f in ("total", "expense_date", "category_id") if getattr(e, f) is None]
    if missing:
        raise Invalid("Missing required fields", code="missing_fields", fields=missing)
    if e.ocr_needs_confirmation and not confirm_low_confidence:
        raise Invalid("OCR fields need human confirmation", code="needs_confirmation")
    if e.payment_method in ("card", "bank_transfer") and not e.bank_account_id:
        raise Invalid("Bank account required for card/transfer payments", code="bank_required", fields=["bank_account_id"])
    e.ocr_needs_confirmation = False
    if e.supplier_name and not e.supplier_id:
        e.supplier_id = _supplier(db, auth.hh, e.supplier_name).id
    e.submitted_at = datetime.now(timezone.utc)
    transition(db, e, "submitted", auth.user.id)
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="expense.submit", entity_type="expense", entity_id=e.id,
          details={"total": str(e.total)})


def _require_approver(auth, e: Expense):
    if auth.user.role not in ADMIN_ROLES:
        raise Forbidden("Only financial admins can do this")
    if e.user_id == auth.user.id:
        raise Forbidden("You cannot approve or reject your own expense", code="self_approval")


def approve(db, auth, e: Expense):
    _require_approver(auth, e)
    transition(db, e, "approved", auth.user.id)
    e.approved_by, e.approved_at = auth.user.id, datetime.now(timezone.utc)
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="expense.approve", entity_type="expense", entity_id=e.id,
          details={"total": str(e.total)})


def reject(db, auth, e: Expense, reason: str):
    _require_approver(auth, e)
    if not reason or not reason.strip():
        raise Invalid("Reason required", code="reason_required")
    transition(db, e, "rejected", auth.user.id, reason)
    e.rejection_reason = reason.strip()[:500]
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="expense.reject", entity_type="expense", entity_id=e.id)


def return_for_correction(db, auth, e: Expense, reason: str):
    _require_approver(auth, e)
    transition(db, e, "needs_review", auth.user.id, reason)
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="expense.return", entity_type="expense", entity_id=e.id)


def reopen_rejected(db, auth, e: Expense):
    if e.user_id != auth.user.id and auth.user.role not in ADMIN_ROLES:
        raise Forbidden("Not allowed")
    transition(db, e, "draft", auth.user.id)
    e.rejection_reason = None


def refunded_total(db, original_id) -> Decimal:
    v = db.scalar(select(func.coalesce(func.sum(Expense.total), 0)).where(
        Expense.refund_of_id == original_id, Expense.status.notin_(("rejected", "reversed"))))
    return Decimal(v)


def _expense_lines(db, e: Expense) -> tuple[list[Line], str]:
    cat = db.get(Category, e.category_id)
    if not cat or not cat.account_id:
        raise Invalid("Category has no account", code="category_not_found")
    exp_acc = cat.account_id
    amt = e.total
    if e.payment_method == "cash":
        other = acc.wallet_for(db, e.household_id, e.user_id).id
        ttype = "cash_expense"
    elif e.payment_method in ("card", "bank_transfer"):
        other = acc.get_bank(db, e.household_id, e.bank_account_id).id
        ttype = "card_expense" if e.payment_method == "card" else "transfer_expense"
    else:
        other = acc.payable_for(db, e.household_id, e.user_id).id
        ttype = "personal_funds_expense"
    if e.is_refund:
        return [Line(other, debit=amt), Line(exp_acc, credit=amt)], "refund"
    return [Line(exp_acc, debit=amt), Line(other, credit=amt)], ttype


def post(db: Session, auth, expense_id):
    if auth.user.role not in ADMIN_ROLES:
        raise Forbidden("Only financial admins can post")
    e = get_expense(db, auth, expense_id, for_update=True)
    if e.status != "approved":
        raise Conflict(f"Only approved expenses can be posted (is {e.status})", code="not_approved")
    if e.user_id == auth.user.id:
        raise Forbidden("You cannot post your own expense", code="self_approval")
    if e.is_refund:
        orig = db.scalar(select(Expense).where(Expense.id == e.refund_of_id).with_for_update())
        if orig.status != "posted":
            raise Conflict("Original expense is not posted", code="original_not_posted")
        others = refunded_total(db, orig.id) - e.total
        if others + e.total > orig.total:
            raise Invalid("Refund exceeds original expense", code="refund_exceeds_original")
    lines, ttype = _expense_lines(db, e)
    txn, replayed = post_transaction(
        db, household_id=e.household_id, type=ttype, lines=lines, key=f"expense-post:{e.id}",
        occurred_at=e.expense_date, description=f"{'Rimbursim' if e.is_refund else 'Shpenzim'}: {e.supplier_name or ''}",
        created_by=auth.user.id, expense_id=e.id)
    e.posted_txn_id = txn.id
    transition(db, e, "posted", auth.user.id)
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="expense.post", entity_type="expense", entity_id=e.id,
          details={"transaction_id": str(txn.id), "total": str(e.total), "method": e.payment_method})
    return e, txn


def reverse(db: Session, auth, expense_id, reason: str):
    if auth.user.role not in ADMIN_ROLES:
        raise Forbidden("Only financial admins can reverse")
    e = get_expense(db, auth, expense_id, for_update=True)
    if e.status != "posted":
        raise Conflict("Only posted expenses can be reversed", code="invalid_transition")
    if not e.is_refund and refunded_total(db, e.id) > 0:
        raise Conflict("Reverse its refunds first", code="has_refunds")
    rev = reverse_transaction(db, e.posted_txn_id, household_id=auth.hh, reason=reason, actor_id=auth.user.id)
    transition(db, e, "reversed", auth.user.id, reason)
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="expense.reverse", entity_type="expense", entity_id=e.id,
          details={"reversal_txn": str(rev.id)})
    return e


def create_refund(db: Session, auth, original_id, amount, notes: str | None, day: date | None):
    if auth.user.role not in ADMIN_ROLES:
        raise Forbidden("Only financial admins can create refunds")
    orig = db.scalar(select(Expense).where(Expense.id == original_id, Expense.household_id == auth.hh).with_for_update())
    if not orig:
        raise NotFound("Expense not found")
    if orig.status != "posted" or orig.is_refund:
        raise Conflict("Refunds can only be created from posted expenses", code="original_not_posted")
    amt = parse_money(amount, field="amount")
    if refunded_total(db, orig.id) + amt > orig.total:
        raise Invalid("Refund exceeds original expense", code="refund_exceeds_original")
    r = Expense(household_id=auth.hh, user_id=orig.user_id, created_by=auth.user.id, category_id=orig.category_id,
                supplier_id=orig.supplier_id, supplier_name=orig.supplier_name, expense_date=day or date.today(),
                total=amt, payment_method=orig.payment_method, bank_account_id=orig.bank_account_id,
                refund_of_id=orig.id, is_refund=True, notes=notes, status="draft")
    db.add(r)
    db.flush()
    db.add(ExpenseStatusHistory(expense_id=r.id, from_status=None, to_status="draft", actor_id=auth.user.id))
    transition(db, r, "submitted", auth.user.id)
    r.submitted_at = datetime.now(timezone.utc)
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="expense.refund_create", entity_type="expense", entity_id=r.id,
          details={"original": str(orig.id), "amount": str(amt)})
    return r


def serialize(e: Expense, db: Session | None = None) -> dict:
    return {
        "id": str(e.id), "user_id": str(e.user_id), "category_id": str(e.category_id) if e.category_id else None,
        "supplier_name": e.supplier_name, "expense_date": e.expense_date.isoformat() if e.expense_date else None,
        "total": None if e.total is None else format(e.total.quantize(Decimal("0.01")), "f"),
        "currency": e.currency, "payment_method": e.payment_method, "status": e.status, "notes": e.notes,
        "rejection_reason": e.rejection_reason, "ocr_needs_confirmation": e.ocr_needs_confirmation,
        "bank_account_id": str(e.bank_account_id) if e.bank_account_id else None,
        "is_refund": e.is_refund, "refund_of_id": str(e.refund_of_id) if e.refund_of_id else None,
        "posted_txn_id": str(e.posted_txn_id) if e.posted_txn_id else None,
        "created_by": str(e.created_by), "created_at": e.created_at.isoformat(),
        "submitted_at": e.submitted_at.isoformat() if e.submitted_at else None,
        "document_count": len(e.documents),
    }
