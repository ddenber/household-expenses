from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import COOKIE, Auth, current_auth
from ..errors import AppError
from ..models import Household, User, now
from ..services.audit import audit
from ..services.security import create_session, rate_limit, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


def user_out(u: User, db: Session) -> dict:
    h = db.get(Household, u.household_id)
    return {"id": str(u.id), "email": u.email, "name": u.name, "role": u.role, "household_id": str(u.household_id),
            "household_name": h.name, "is_demo": h.is_demo}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    st = get_settings()
    ip = request.client.host if request.client else "?"
    rate_limit(f"login:{ip}", st.login_rate_limit_per_min)
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user and user.locked_until and user.locked_until > now():
        raise AppError("Too many failed attempts. Try again later.", code="locked", status=429)
    ok = verify_password(body.password, user.password_hash if user else None)
    if not user or not ok or not user.is_active:
        if user:
            user.failed_logins += 1
            if user.failed_logins >= st.max_failed_logins:
                user.locked_until = now() + timedelta(minutes=st.lockout_minutes)
                user.failed_logins = 0
                audit(db, household_id=user.household_id, actor_id=user.id, action="auth.lockout", entity_type="user", entity_id=user.id)
            db.commit()
        raise AppError("Invalid email or password", code="invalid_credentials", status=401)
    user.failed_logins, user.locked_until = 0, None
    token, s = create_session(db, user)
    audit(db, household_id=user.household_id, actor_id=user.id, action="auth.login", entity_type="user", entity_id=user.id)
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=st.cookie_secure,
                        max_age=st.session_hours * 3600, path="/")
    return {"user": user_out(user, db), "csrf_token": s.csrf_token}


@router.post("/logout")
def logout(response: Response, auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    auth.session.revoked_at = now()
    db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    return {"user": user_out(auth.user, db), "csrf_token": auth.session.csrf_token}
