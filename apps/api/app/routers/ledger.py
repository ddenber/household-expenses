import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Auth, require
from ..errors import NotFound
from ..models import Account, FinancialTransaction
from ..money import fmt
from ..services import operations as ops
from ..services.audit import audit
from ..services.ledger import reverse_transaction

router = APIRouter(prefix="/ledger", tags=["ledger"])


class Base(BaseModel):
    idempotency_key: str
    date: date
    amount: str | int


class OpeningIn(Base):
    bank_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


class FundingIn(Base):
    bank_id: uuid.UUID
    description: str = ""


class AtmIn(Base):
    bank_id: uuid.UUID
    user_id: uuid.UUID
    fee: str | int | None = None


class ReturnIn(Base):
    bank_id: uuid.UUID
    user_id: uuid.UUID


class TransferIn(Base):
    from_user_id: uuid.UUID
    to_user_id: uuid.UUID


class ReimburseIn(Base):
    bank_id: uuid.UUID
    user_id: uuid.UUID


def txn_out(t: FinancialTransaction, names: dict | None = None) -> dict:
    return {"id": str(t.id), "type": t.type, "status": t.status, "date": t.occurred_at.isoformat(), "description": t.description,
            "expense_id": str(t.expense_id) if t.expense_id else None, "reverses_id": str(t.reverses_id) if t.reverses_id else None,
            "reversed_by_id": str(t.reversed_by_id) if t.reversed_by_id else None, "reason": t.reason,
            "lines": [{"account_id": str(l.account_id), "account": (names or {}).get(l.account_id), "debit": fmt(l.debit),
                       "credit": fmt(l.credit)} for l in t.lines]}


def _res(db, txn, replayed, **extra):
    db.commit()
    return {"transaction": txn_out(txn), "replayed": replayed, **extra}


@router.post("/opening-balance", status_code=201)
def opening(b: OpeningIn, auth: Auth = Depends(require("ledger.write")), db: Session = Depends(get_db)):
    t, r = ops.opening_balance(db, auth.user, key=b.idempotency_key, day=b.date, amount=b.amount, bank_id=b.bank_id, user_id=b.user_id)
    return _res(db, t, r)


@router.post("/funding", status_code=201)
def funding(b: FundingIn, auth: Auth = Depends(require("ledger.write")), db: Session = Depends(get_db)):
    t, r = ops.funding(db, auth.user, key=b.idempotency_key, day=b.date, amount=b.amount, bank_id=b.bank_id, description=b.description)
    return _res(db, t, r)


@router.post("/atm-withdrawal", status_code=201)
def atm(b: AtmIn, auth: Auth = Depends(require("ledger.write")), db: Session = Depends(get_db)):
    t, fee, r = ops.atm_withdrawal(db, auth.user, key=b.idempotency_key, day=b.date, amount=b.amount, bank_id=b.bank_id,
                                   user_id=b.user_id, fee=b.fee)
    return _res(db, t, r, fee_transaction=txn_out(fee) if fee else None)


@router.post("/cash-return", status_code=201)
def cash_return(b: ReturnIn, auth: Auth = Depends(require("ledger.write")), db: Session = Depends(get_db)):
    t, r = ops.cash_return(db, auth.user, key=b.idempotency_key, day=b.date, amount=b.amount, bank_id=b.bank_id, user_id=b.user_id)
    return _res(db, t, r)


@router.post("/employee-transfer", status_code=201)
def transfer(b: TransferIn, auth: Auth = Depends(require("ledger.write")), db: Session = Depends(get_db)):
    t, r = ops.employee_transfer(db, auth.user, key=b.idempotency_key, day=b.date, amount=b.amount,
                                 from_user_id=b.from_user_id, to_user_id=b.to_user_id)
    return _res(db, t, r)


@router.post("/reimbursement", status_code=201)
def reimburse(b: ReimburseIn, auth: Auth = Depends(require("ledger.write")), db: Session = Depends(get_db)):
    t, r = ops.reimbursement(db, auth.user, key=b.idempotency_key, day=b.date, amount=b.amount, bank_id=b.bank_id, user_id=b.user_id)
    return _res(db, t, r)


class ReverseIn(BaseModel):
    reason: str


@router.post("/transactions/{tid}/reverse", status_code=201)
def reverse(tid: uuid.UUID, b: ReverseIn, auth: Auth = Depends(require("ledger.write")), db: Session = Depends(get_db)):
    rev = reverse_transaction(db, tid, household_id=auth.hh, reason=b.reason, actor_id=auth.user.id)
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="ledger.reverse", entity_type="financial_transaction",
          entity_id=tid, details={"reversal": str(rev.id)})
    db.commit()
    return {"transaction": txn_out(rev)}


@router.get("/transactions")
def list_txns(auth: Auth = Depends(require("ledger.read")), db: Session = Depends(get_db), type: str | None = None,
              account_id: uuid.UUID | None = None, date_from: date | None = None, date_to: date | None = None,
              expense_id: uuid.UUID | None = None, limit: int = Query(100, le=500), offset: int = 0):
    q = select(FinancialTransaction).where(FinancialTransaction.household_id == auth.hh)
    if type:
        q = q.where(FinancialTransaction.type == type)
    if date_from:
        q = q.where(FinancialTransaction.occurred_at >= date_from)
    if date_to:
        q = q.where(FinancialTransaction.occurred_at <= date_to)
    if expense_id:
        q = q.where(FinancialTransaction.expense_id == expense_id)
    if account_id:
        from ..models import JournalLine
        q = q.where(FinancialTransaction.id.in_(select(JournalLine.transaction_id).where(JournalLine.account_id == account_id)))
    q = q.order_by(FinancialTransaction.occurred_at.desc(), FinancialTransaction.created_at.desc()).limit(limit).offset(offset)
    names = {a.id: a.name for a in db.scalars(select(Account).where(Account.household_id == auth.hh))}
    return [txn_out(t, names) for t in db.scalars(q)]


@router.get("/transactions/{tid}")
def get_txn(tid: uuid.UUID, auth: Auth = Depends(require("ledger.read")), db: Session = Depends(get_db)):
    t = db.get(FinancialTransaction, tid)
    if not t or t.household_id != auth.hh:
        raise NotFound("Transaction not found")
    names = {a.id: a.name for a in db.scalars(select(Account).where(Account.household_id == auth.hh))}
    return txn_out(t, names)
