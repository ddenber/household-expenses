import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Auth, current_auth, require
from ..models import Account, AuditLog, Expense, FinancialTransaction, User
from ..money import fmt
from ..services import accounts as acc
from ..services import reports as rep
from ..services.reconciliation import month_bounds

router = APIRouter(tags=["reports"])


def _agg(db, hh, statuses, start=None, end=None, user_id=None):
    q = select(func.coalesce(func.sum(Expense.total), 0), func.count()).where(
        Expense.household_id == hh, Expense.status.in_(statuses), Expense.is_refund.is_(False))
    if start:
        q = q.where(Expense.expense_date >= start, Expense.expense_date <= end)
    if user_id:
        q = q.where(Expense.user_id == user_id)
    s, c = db.execute(q).one()
    return fmt(Decimal(s)), c


@router.get("/dashboard/admin")
def admin_dashboard(auth: Auth = Depends(require("dashboard.admin")), db: Session = Depends(get_db)):
    hh = auth.hh
    today = date.today()
    start, end = month_bounds(today.year, today.month)
    bal = acc.balances(db, hh)
    accounts = list(db.scalars(select(Account).where(Account.household_id == hh)))
    bank_total = sum((bal.get(a.id, Decimal(0)) for a in accounts if a.kind == "bank"), Decimal(0))
    wallets = [a for a in accounts if a.kind == "employee_wallet"]
    cash_total = sum((bal.get(a.id, Decimal(0)) for a in wallets), Decimal(0))
    susp = next((a for a in accounts if a.kind == "suspense"), None)
    payable = sum((-bal.get(a.id, Decimal(0)) for a in accounts if a.kind == "reimbursement_payable"), Decimal(0))
    fees = sum((bal.get(a.id, Decimal(0)) for a in accounts if a.kind == "bank_fees"), Decimal(0))
    pend_amt, pend_n = _agg(db, hh, ("submitted",))
    appr_amt, appr_n = _agg(db, hh, ("approved",))
    month_amt, month_n = _agg(db, hh, ("posted",), start, end)
    month_net = sum((bal.get(a.id, Decimal(0)) for a in accounts if a.kind == "expense_category"), Decimal(0))
    kpis = [
        {"key": "bank_balance", "value": fmt(bank_total), "link": {"path": "/admin/llogarite"}},
        {"key": "cash_with_employees", "value": fmt(cash_total), "link": {"path": "/admin/llogarite", "params": {"kind": "employee_wallet"}}},
        {"key": "pending_approval", "value": pend_amt, "count": pend_n, "link": {"path": "/admin/shpenzimet", "params": {"status": "submitted"}}},
        {"key": "approved_not_posted", "value": appr_amt, "count": appr_n, "link": {"path": "/admin/shpenzimet", "params": {"status": "approved"}}},
        {"key": "month_expenses", "value": month_amt, "count": month_n,
         "link": {"path": "/admin/shpenzimet", "params": {"status": "posted", "date_from": start.isoformat(), "date_to": end.isoformat()}}},
        {"key": "total_expenses_net", "value": fmt(month_net), "link": {"path": "/admin/analitika"}},
        {"key": "bank_fees", "value": fmt(fees), "link": {"path": "/admin/librat", "params": {"type": "bank_fee"}}},
        {"key": "reimbursements_owed", "value": fmt(payable), "link": {"path": "/admin/librat", "params": {"type": "personal_funds_expense"}}},
        {"key": "suspense", "value": fmt(bal.get(susp.id, Decimal(0))) if susp else "0.00",
         "link": {"path": "/admin/librat", "params": {"type": "cash_difference"}}},
    ]
    users = {u.id: u.name for u in db.scalars(select(User).where(User.household_id == hh))}
    return {"month": f"{today.year}-{today.month:02d}", "kpis": kpis,
            "wallets": [{"user_id": str(a.owner_user_id), "name": users.get(a.owner_user_id), "balance": fmt(bal.get(a.id, 0)),
                         "account_id": str(a.id)} for a in wallets],
            "negative_balances": [a.name for a in accounts if a.type == "asset" and bal.get(a.id, Decimal(0)) < 0]}


@router.get("/dashboard/employee")
def employee_dashboard(auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    today = date.today()
    start, end = month_bounds(today.year, today.month)
    uid = auth.user.id
    wallet = acc.wallet_for(db, auth.hh, uid) if auth.user.role == "employee" else None
    pend_amt, pend_n = _agg(db, auth.hh, ("draft", "uploaded", "processing", "needs_review", "submitted"), user_id=uid)
    m_amt, m_n = _agg(db, auth.hh, ("approved", "posted"), start, end, user_id=uid)
    from ..services.expenses import serialize
    recent = db.scalars(select(Expense).where(Expense.user_id == uid).order_by(Expense.created_at.desc()).limit(5)).all()
    return {"cash_balance": fmt(acc.balance(db, wallet.id)) if wallet else None, "pending": {"amount": pend_amt, "count": pend_n},
            "month_total": {"amount": m_amt, "count": m_n}, "recent": [serialize(e) for e in recent]}


@router.get("/analytics/spend")
def analytics(group: str = "category", date_from: date | None = None, date_to: date | None = None,
              auth: Auth = Depends(require("dashboard.admin")), db: Session = Depends(get_db)):
    return rep.spend_by(db, auth.hh, "supplier" if group == "supplier" else "category", date_from, date_to)


def _file(name, fmt_, headers, rows, title):
    if fmt_ == "xlsx":
        return Response(rep.table_to_xlsx(title, headers, rows),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
    return Response(rep.table_to_csv(headers, rows), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


@router.get("/exports/expenses")
def export_expenses(format: str = "csv", user_id: uuid.UUID | None = None, status: str | None = None,
                    date_from: date | None = None, date_to: date | None = None,
                    auth: Auth = Depends(require("export")), db: Session = Depends(get_db)):
    h, r = rep.expense_rows(db, auth.hh, user_id, status, date_from, date_to)
    return _file("shpenzimet", format, h, r, "Shpenzimet")


@router.get("/exports/transactions")
def export_txns(format: str = "csv", type: str | None = None, date_from: date | None = None, date_to: date | None = None,
                auth: Auth = Depends(require("export")), db: Session = Depends(get_db)):
    h, r = rep.transaction_rows(db, auth.hh, date_from, date_to, type)
    return _file("libri", format, h, r, "Libri")


@router.get("/audit")
def audit_log(limit: int = 200, offset: int = 0, action: str | None = None,
              auth: Auth = Depends(require("audit.read")), db: Session = Depends(get_db)):
    q = select(AuditLog).where(AuditLog.household_id == auth.hh)
    if action:
        q = q.where(AuditLog.action.like(f"{action}%"))
    rows = db.scalars(q.order_by(AuditLog.id.desc()).limit(min(limit, 500)).offset(offset))
    return [{"id": r.id, "at": r.at.isoformat(), "actor_id": str(r.actor_id) if r.actor_id else None, "action": r.action,
             "entity_type": r.entity_type, "entity_id": r.entity_id, "details": r.details} for r in rows]
