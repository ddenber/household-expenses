"""Cash-handling operations expressed as ledger postings. None of these create expenses
(except the ATM fee, which is a separate bank-fee transaction)."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import Invalid
from ..models import Account, User
from ..money import parse_money
from . import accounts as acc
from .audit import audit
from .ledger import Line, post_transaction


def _employee(db, hh, user_id) -> User:
    u = db.get(User, user_id)
    if not u or u.household_id != hh or not u.is_active:
        raise Invalid("Employee not found", code="employee_not_found")
    if u.role != "employee":
        raise Invalid("Wallet operations require an employee", code="not_employee")
    return u


def _post(db, actor, type_, lines, key, day, desc, **kw):
    txn, replayed = post_transaction(
        db, household_id=actor.household_id, type=type_, lines=lines, key=key, occurred_at=day,
        description=desc, created_by=actor.id, **kw)
    if not replayed:
        audit(db, household_id=actor.household_id, actor_id=actor.id, action=f"ledger.{type_}",
              entity_type="financial_transaction", entity_id=txn.id,
              details={"amount": str(sum(l.debit for l in lines)), "date": str(day)})
    return txn, replayed


def opening_balance(db, actor, *, key, day: date, amount, bank_id=None, user_id=None):
    amt = parse_money(amount)
    if bool(bank_id) == bool(user_id):
        raise Invalid("Provide exactly one of bank_id or user_id", code="bad_target")
    if bank_id:
        target = acc.get_bank(db, actor.household_id, bank_id)
    else:
        _employee(db, actor.household_id, user_id)
        target = acc.wallet_for(db, actor.household_id, user_id)
    eq = acc.system_account(db, actor.household_id, "opening_equity")
    return _post(db, actor, "opening_balance", [Line(target.id, debit=amt), Line(eq.id, credit=amt)], key, day,
                 "Gjendje fillestare")


def funding(db, actor, *, key, day, amount, bank_id, description=""):
    amt = parse_money(amount)
    bank = acc.get_bank(db, actor.household_id, bank_id)
    src = acc.system_account(db, actor.household_id, "owner_funding")
    return _post(db, actor, "funding", [Line(bank.id, debit=amt), Line(src.id, credit=amt)], key, day,
                 description or "Financim i llogarisë bankare")


def atm_withdrawal(db, actor, *, key, day, amount, bank_id, user_id, fee=None, description=""):
    amt = parse_money(amount)
    fee_amt = parse_money(fee) if fee not in (None, "", 0, "0") else None
    _employee(db, actor.household_id, user_id)
    bank = acc.get_bank(db, actor.household_id, bank_id)
    wallet = acc.wallet_for(db, actor.household_id, user_id)
    txn, rep = _post(db, actor, "atm_withdrawal", [Line(wallet.id, debit=amt), Line(bank.id, credit=amt)], key, day,
                     description or "Terheqje ATM")
    fee_txn = None
    if fee_amt:
        fees = acc.system_account(db, actor.household_id, "bank_fees")
        fee_txn, _ = _post(db, actor, "bank_fee", [Line(fees.id, debit=fee_amt), Line(bank.id, credit=fee_amt)],
                           f"{key}:fee", day, "Komision ATM")
    return txn, fee_txn, rep


def cash_return(db, actor, *, key, day, amount, bank_id, user_id):
    amt = parse_money(amount)
    _employee(db, actor.household_id, user_id)
    bank = acc.get_bank(db, actor.household_id, bank_id)
    wallet = acc.wallet_for(db, actor.household_id, user_id)
    return _post(db, actor, "cash_return", [Line(bank.id, debit=amt), Line(wallet.id, credit=amt)], key, day,
                 "Kthim cash ne banke")


def employee_transfer(db, actor, *, key, day, amount, from_user_id, to_user_id):
    amt = parse_money(amount)
    if from_user_id == to_user_id:
        raise Invalid("Cannot transfer to the same employee", code="same_employee")
    _employee(db, actor.household_id, from_user_id)
    _employee(db, actor.household_id, to_user_id)
    a = acc.wallet_for(db, actor.household_id, from_user_id)
    b = acc.wallet_for(db, actor.household_id, to_user_id)
    return _post(db, actor, "employee_transfer", [Line(b.id, debit=amt), Line(a.id, credit=amt)], key, day,
                 "Transferim mes punonjesve")


def reimbursement(db, actor, *, key, day, amount, bank_id, user_id):
    amt = parse_money(amount)
    u = db.get(User, user_id)
    if not u or u.household_id != actor.household_id:
        raise Invalid("User not found")
    bank = acc.get_bank(db, actor.household_id, bank_id)
    pay = acc.payable_for(db, actor.household_id, user_id)
    db.execute(select(Account).where(Account.id == pay.id).with_for_update())
    owed = -acc.balance(db, pay.id)
    if amt > owed:
        raise Invalid(f"Reimbursement exceeds amount owed ({owed})", code="exceeds_payable")
    return _post(db, actor, "reimbursement", [Line(pay.id, debit=amt), Line(bank.id, credit=amt)], key, day,
                 "Rimbursim punonjesi")
