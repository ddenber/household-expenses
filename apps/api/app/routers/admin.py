import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Auth, current_auth, require
from ..errors import Forbidden, Invalid, NotFound
from ..models import Account, Category, Household, User
from ..money import fmt
from ..rbac import EMPLOYEE, ROLES, SUPER_ADMIN
from ..services import accounts as acc
from ..services.audit import audit
from ..services.security import hash_password

router = APIRouter(tags=["admin"])


class UserIn(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=10, max_length=200)
    role: str = EMPLOYEE


def u_out(u: User):
    return {"id": str(u.id), "email": u.email, "name": u.name, "role": u.role, "is_active": u.is_active}


@router.get("/users")
def list_users(auth: Auth = Depends(require("user.list")), db: Session = Depends(get_db)):
    return [u_out(u) for u in db.scalars(select(User).where(User.household_id == auth.hh).order_by(User.name))]


@router.post("/users", status_code=201)
def create_user(body: UserIn, auth: Auth = Depends(require("user.manage")), db: Session = Depends(get_db)):
    if body.role not in ROLES:
        raise Invalid("Unknown role", code="bad_role")
    if body.role != EMPLOYEE and auth.user.role != SUPER_ADMIN:
        raise Forbidden("Only a super admin can create privileged users", code="forbidden")
    email = body.email.strip().lower()
    if "@" not in email or db.scalar(select(User).where(User.email == email)):
        raise Invalid("Invalid or already used email", code="bad_email")
    u = User(household_id=auth.hh, email=email, name=body.name.strip(), role=body.role, password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    if u.role == EMPLOYEE:
        acc.wallet_for(db, auth.hh, u.id)
        acc.payable_for(db, auth.hh, u.id)
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="user.create", entity_type="user", entity_id=u.id, details={"role": u.role})
    db.commit()
    return u_out(u)


class UserPatch(BaseModel):
    is_active: bool


@router.patch("/users/{user_id}")
def patch_user(user_id: uuid.UUID, body: UserPatch, auth: Auth = Depends(require("user.manage")), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u or u.household_id != auth.hh:
        raise NotFound("User not found")
    if u.id == auth.user.id:
        raise Invalid("Cannot deactivate yourself", code="self_deactivate")
    if u.role != EMPLOYEE and auth.user.role != SUPER_ADMIN:
        raise Forbidden("Only a super admin can change privileged users")
    u.is_active = body.is_active
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="user.set_active", entity_type="user", entity_id=u.id, details={"active": body.is_active})
    db.commit()
    return u_out(u)


class HouseholdIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    admin_email: str
    admin_name: str
    admin_password: str = Field(min_length=10)


@router.post("/households", status_code=201)
def create_household(body: HouseholdIn, auth: Auth = Depends(require("household.create")), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.admin_email.strip().lower())):
        raise Invalid("Email already used", code="bad_email")
    h = Household(name=body.name.strip())
    db.add(h)
    db.flush()
    acc.seed_default_categories(db, h.id)
    a = User(household_id=h.id, email=body.admin_email.strip().lower(), name=body.admin_name, role="financial_admin",
             password_hash=hash_password(body.admin_password))
    db.add(a)
    audit(db, household_id=h.id, actor_id=auth.user.id, action="household.create", entity_type="household", entity_id=h.id)
    db.commit()
    return {"id": str(h.id), "name": h.name}


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.get("/categories")
def list_categories(auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    cs = db.scalars(select(Category).where(Category.household_id == auth.hh, Category.is_active).order_by(Category.name)).all()
    return [{"id": str(c.id), "name": c.name} for c in cs]


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, auth: Auth = Depends(require("category.manage")), db: Session = Depends(get_db)):
    c = acc.create_category(db, auth.hh, body.name)
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="category.create", entity_type="category", entity_id=c.id)
    db.commit()
    return {"id": str(c.id), "name": c.name}


@router.delete("/categories/{cid}")
def archive_category(cid: uuid.UUID, auth: Auth = Depends(require("category.manage")), db: Session = Depends(get_db)):
    c = db.get(Category, cid)
    if not c or c.household_id != auth.hh:
        raise NotFound("Category not found")
    c.is_active = False
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="category.archive", entity_type="category", entity_id=c.id)
    db.commit()
    return {"ok": True}


class BankIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@router.post("/bank-accounts", status_code=201)
def create_bank(body: BankIn, auth: Auth = Depends(require("ledger.write")), db: Session = Depends(get_db)):
    a = acc.create_bank_account(db, auth.hh, body.name.strip())
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="bank_account.create", entity_type="account", entity_id=a.id)
    db.commit()
    return {"id": str(a.id), "name": a.name}


@router.get("/accounts")
def list_accounts(auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    """Admin/auditor: all accounts with ledger-derived balances. Employee: only own wallet."""
    bal = acc.balances(db, auth.hh)
    q = select(Account).where(Account.household_id == auth.hh, Account.is_active)
    out = []
    for a in db.scalars(q.order_by(Account.kind, Account.name)):
        if auth.user.role == EMPLOYEE and not (a.kind == "employee_wallet" and a.owner_user_id == auth.user.id):
            continue
        if a.kind == "expense_category" and auth.user.role == EMPLOYEE:
            continue
        b = bal.get(a.id, 0)
        out.append({"id": str(a.id), "name": a.name, "type": a.type, "kind": a.kind,
                    "owner_user_id": str(a.owner_user_id) if a.owner_user_id else None, "balance": fmt(b)})
    return out
