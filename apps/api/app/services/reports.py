import csv
import io
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Account, Category, Expense, FinancialTransaction, JournalLine, Supplier, User,
)
from ..money import fmt
from . import accounts as acc


def table_to_csv(headers, rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow([("'" + c if isinstance(c, str) and c[:1] in "=+-@" else c) for c in r])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def table_to_xlsx(title, headers, rows) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = title[:30]
    ws.append(headers)
    for r in rows:
        ws.append([("'" + c if isinstance(c, str) and c[:1] in "=+-@" else c) for c in r])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def expense_rows(db: Session, hh, user_id=None, status=None, date_from=None, date_to=None):
    q = select(Expense, Category.name, User.name).join(User, User.id == Expense.user_id).outerjoin(
        Category, Category.id == Expense.category_id).where(Expense.household_id == hh).order_by(Expense.expense_date.desc().nullslast())
    if user_id:
        q = q.where(Expense.user_id == user_id)
    if status:
        q = q.where(Expense.status == status)
    if date_from:
        q = q.where(Expense.expense_date >= date_from)
    if date_to:
        q = q.where(Expense.expense_date <= date_to)
    headers = ["id", "date", "employee", "supplier", "category", "payment_method", "total", "currency", "status", "is_refund", "ledger_txn_id"]
    rows = [[str(e.id), e.expense_date.isoformat() if e.expense_date else "", un, e.supplier_name or "", cn or "",
             e.payment_method, fmt(e.total) or "", e.currency, e.status, e.is_refund, str(e.posted_txn_id or "")]
            for e, cn, un in db.execute(q).all()]
    return headers, rows


def transaction_rows(db: Session, hh, date_from=None, date_to=None, type_=None):
    q = select(FinancialTransaction).where(FinancialTransaction.household_id == hh).order_by(
        FinancialTransaction.occurred_at, FinancialTransaction.created_at)
    if date_from:
        q = q.where(FinancialTransaction.occurred_at >= date_from)
    if date_to:
        q = q.where(FinancialTransaction.occurred_at <= date_to)
    if type_:
        q = q.where(FinancialTransaction.type == type_)
    names = {a.id: a.name for a in db.scalars(select(Account).where(Account.household_id == hh))}
    headers = ["txn_id", "date", "type", "status", "description", "account", "debit", "credit", "currency", "expense_id"]
    rows = []
    for t in db.scalars(q):
        for l in t.lines:
            rows.append([str(t.id), t.occurred_at.isoformat(), t.type, t.status, t.description, names.get(l.account_id, ""),
                         fmt(l.debit), fmt(l.credit), l.currency, str(t.expense_id or "")])
    return headers, rows


def spend_by(db: Session, hh, group: str, date_from=None, date_to=None) -> list[dict]:
    """Analytics derived from the LEDGER (expense-category accounts), so reversals/refunds are netted."""
    amount = func.sum(JournalLine.debit - JournalLine.credit)
    if group == "category":
        q = select(Category.id, Category.name, amount).select_from(JournalLine).join(
            FinancialTransaction, FinancialTransaction.id == JournalLine.transaction_id).join(
            Account, Account.id == JournalLine.account_id).join(Category, Category.account_id == Account.id).where(
            FinancialTransaction.household_id == hh)
        if date_from:
            q = q.where(FinancialTransaction.occurred_at >= date_from)
        if date_to:
            q = q.where(FinancialTransaction.occurred_at <= date_to)
        q = q.group_by(Category.id, Category.name).order_by(amount.desc())
        return [{"id": str(i), "name": n, "total": fmt(Decimal(t))} for i, n, t in db.execute(q).all() if t]
    q = select(Supplier.id, Supplier.name, amount).select_from(JournalLine).join(
        FinancialTransaction, FinancialTransaction.id == JournalLine.transaction_id).join(
        Account, Account.id == JournalLine.account_id).join(Expense, Expense.id == FinancialTransaction.expense_id).join(
        Supplier, Supplier.id == Expense.supplier_id).where(
        FinancialTransaction.household_id == hh, Account.kind == "expense_category")
    if date_from:
        q = q.where(FinancialTransaction.occurred_at >= date_from)
    if date_to:
        q = q.where(FinancialTransaction.occurred_at <= date_to)
    q = q.group_by(Supplier.id, Supplier.name).order_by(amount.desc())
    return [{"id": str(i), "name": n, "total": fmt(Decimal(t))} for i, n, t in db.execute(q).all() if t]


def reconciliation_pdf(c: dict, household_name: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    st = getSampleStyleSheet()
    rows = [
        ["Gjendja hapese / Opening", c["opening"]], ["+ Terheqje ATM", c["withdrawals"]],
        ["+ Transferime te marra", c["transfers_in"]], ["+ Burime te tjera", c["other_sources"]],
        ["+ Rimbursime", c["refunds"]], ["- Shpenzime cash te miratuara", c["cash_expenses"]],
        ["- Kthime ne banke", c["returns_to_bank"]], ["- Transferime dalese", c["transfers_out"]],
        ["- Dalje te tjera", c["other_outflows"]], ["= Mbyllja e pritur / Expected", c["expected_closing"]],
        ["Numerimi i deklaruar / Declared", c["declared_count"] or "-"], ["Diferenca / Difference", c["difference"] or "-"],
        ["Rregullim diference (suspense)", c["count_adjustment"]],
    ]
    side = [
        ["Ne pritje (jo e postuar)", f'{c["pending"]["amount"]} ({c["pending"]["count"]})'],
        ["Miratuar, pa postuar", f'{c["approved_not_posted"]["amount"]} ({c["approved_not_posted"]["count"]})'],
        ["Refuzuar", f'{c["rejected"]["amount"]} ({c["rejected"]["count"]})'],
        ["Fatura qe mungojne", str(c["missing_receipts"])], ["Suspense (shtepia)", c["suspense_balance"]],
    ]
    ts = TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("ALIGN", (1, 0), (1, -1), "RIGHT")])
    t1, t2 = Table(rows, colWidths=[300, 120]), Table(side, colWidths=[300, 120])
    t1.setStyle(ts)
    t2.setStyle(ts)
    story = [Paragraph(f"Pasqyra e arkes - {c['user_name']} - {c['month']:02d}/{c['year']}", st["Title"]),
             Paragraph(f"{household_name} - Statusi: {c['status']} - EUR", st["Normal"]), Spacer(1, 12), t1, Spacer(1, 16),
             Paragraph("Te raportuara ndarazi (nuk futen ne mbylljen e pritur)", st["Heading3"]), t2]
    doc.build(story)
    return buf.getvalue()
