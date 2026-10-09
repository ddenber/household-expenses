import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..errors import Invalid, NotFound
from ..models import Account, Category, FinancialTransaction, JournalLine, User

DEFAULT_CATEGORIES = [
    "Ushqimore", "Pije", "Restorante", "Produkte Higjienike", "Mirëmbajtje Shtëpie", "Pajisje Shtëpiake",
    "Mobilie", "Elektronikë", "Veshmbathje", "Shëndetësia", "Barnatore", "Transport", "Karburant",
    "Shërbime", "Riparime", "Udhëtime", "Dhurata", "Shpenzime Personale", "Shpenzime për Fëmijë",
    "Shpenzime të Tjera",
]


def get_or_create_account(db: Session, household_id, code: str, name: str, type_: str, kind: str, owner_user_id=None) -> Account:
    acc = db.scalar(select(Account).where(Account.household_id == household_id, Account.code == code))
    if acc:
        return acc
    acc = Account(household_id=household_id, code=code, name=name, type=type_, kind=kind, owner_user_id=owner_user_id)
    try:
        with db.begin_nested():
            db.add(acc)
            db.flush()
    except IntegrityError:
        return db.scalar(select(Account).where(Account.household_id == household_id, Account.code == code))
    return acc


def system_account(db, hh, kind: str) -> Account:
    spec = {
        "suspense": ("Suspense / Diferenca e pashpjeguar", "suspense"),
        "bank_fees": ("Komisione bankare", "expense"),
        "opening_equity": ("Kapitali fillestar", "equity"),
        "owner_funding": ("Financim nga pronari", "equity"),
    }[kind]
    return get_or_create_account(db, hh, kind, spec[0], spec[1], kind)


def wallet_for(db: Session, hh, user_id) -> Account:
    u = db.get(User, user_id)
    if not u or u.household_id != hh:
        raise NotFound("User not found")
    return get_or_create_account(db, hh, f"wallet:{user_id}", f"Arka cash – {u.name}", "asset", "employee_wallet", user_id)


def payable_for(db: Session, hh, user_id) -> Account:
    u = db.get(User, user_id)
    if not u or u.household_id != hh:
        raise NotFound("User not found")
    return get_or_create_account(db, hh, f"payable:{user_id}", f"Detyrim rimbursimi – {u.name}", "liability", "reimbursement_payable", user_id)


def create_bank_account(db: Session, hh, name: str) -> Account:
    code = f"bank:{uuid.uuid4()}"
    return get_or_create_account(db, hh, code, name, "asset", "bank")


def default_bank(db: Session, hh) -> Account | None:
    banks = db.scalars(select(Account).where(Account.household_id == hh, Account.kind == "bank", Account.is_active)).all()
    return banks[0] if len(banks) == 1 else None


def get_bank(db: Session, hh, bank_id) -> Account:
    acc = db.get(Account, bank_id) if bank_id else None
    if not acc or acc.household_id != hh or acc.kind != "bank":
        raise Invalid("Bank account not found", code="bank_not_found")
    return acc


def create_category(db: Session, hh, name: str) -> Category:
    name = name.strip()
    if not name:
        raise Invalid("Name required")
    if db.scalar(select(Category).where(Category.household_id == hh, func.lower(Category.name) == name.lower())):
        raise Invalid("Category exists", code="category_exists")
    cat = Category(household_id=hh, name=name)
    db.add(cat)
    db.flush()
    acc = get_or_create_account(db, hh, f"expense:{cat.id}", f"Shpenzim – {name}", "expense", "expense_category")
    cat.account_id = acc.id
    return cat


def seed_default_categories(db: Session, hh) -> None:
    for n in DEFAULT_CATEGORIES:
        create_category(db, hh, n)


def balance(db: Session, account_id, *, before: date | None = None, upto: date | None = None) -> Decimal:
    q = select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)).join(
        FinancialTransaction, FinancialTransaction.id == JournalLine.transaction_id
    ).where(JournalLine.account_id == account_id)
    if before:
        q = q.where(FinancialTransaction.occurred_at < before)
    if upto:
        q = q.where(FinancialTransaction.occurred_at <= upto)
    return Decimal(db.scalar(q))


def balances(db: Session, hh) -> dict:
    rows = db.execute(
        select(JournalLine.account_id, func.sum(JournalLine.debit - JournalLine.credit))
        .join(FinancialTransaction, FinancialTransaction.id == JournalLine.transaction_id)
        .where(FinancialTransaction.household_id == hh).group_by(JournalLine.account_id)
    ).all()
    return {r[0]: Decimal(r[1]) for r in rows}
