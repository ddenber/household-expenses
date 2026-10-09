import uuid
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Auth, current_auth, require
from ..errors import NotFound
from ..models import Household, Reconciliation, User
from ..rbac import can
from ..services import reconciliation as svc
from ..services.reports import reconciliation_pdf

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


class DeclareIn(BaseModel):
    user_id: uuid.UUID | None = None
    year: int
    month: int
    amount: str | int


class CloseIn(BaseModel):
    user_id: uuid.UUID
    year: int
    month: int
    post_difference: bool = False
    note: str | None = None


class ReopenIn(BaseModel):
    user_id: uuid.UUID
    year: int
    month: int
    reason: str


def _target(auth: Auth, user_id):
    uid = user_id or auth.user.id
    if uid != auth.user.id and not can(auth.user.role, "reconciliation.read_all"):
        raise NotFound("Not found")
    return uid


@router.get("")
def get(year: int, month: int, user_id: uuid.UUID | None = None, auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    return svc.compute(db, auth.hh, _target(auth, user_id), year, month)


@router.get("/overview")
def overview(year: int, month: int, auth: Auth = Depends(require("reconciliation.read_all")), db: Session = Depends(get_db)):
    emps = db.scalars(select(User).where(User.household_id == auth.hh, User.role == "employee", User.is_active).order_by(User.name))
    return [svc.compute(db, auth.hh, u.id, year, month) for u in emps]


@router.post("/declare")
def declare(b: DeclareIn, auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    r = svc.declare(db, auth, b.user_id or auth.user.id, b.year, b.month, b.amount)
    db.commit()
    return svc.compute(db, auth.hh, r.user_id, b.year, b.month)


@router.post("/close")
def close(b: CloseIn, auth: Auth = Depends(require("reconciliation.close")), db: Session = Depends(get_db)):
    svc.close(db, auth, b.user_id, b.year, b.month, b.post_difference, b.note)
    db.commit()
    return svc.compute(db, auth.hh, b.user_id, b.year, b.month)


@router.post("/reopen")
def reopen(b: ReopenIn, auth: Auth = Depends(require("reconciliation.close")), db: Session = Depends(get_db)):
    svc.reopen(db, auth, b.user_id, b.year, b.month, b.reason)
    db.commit()
    return svc.compute(db, auth.hh, b.user_id, b.year, b.month)


@router.get("/statement.pdf")
def statement(year: int, month: int, user_id: uuid.UUID | None = None, auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    c = svc.compute(db, auth.hh, _target(auth, user_id), year, month)
    h = db.get(Household, auth.hh)
    return Response(reconciliation_pdf(c, h.name), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="pasqyra-{year}-{month:02d}.pdf"'})
