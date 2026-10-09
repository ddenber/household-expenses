import hmac
from dataclasses import dataclass

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .errors import AppError, Forbidden
from .models import Session, User
from .rbac import ADMIN_ROLES, can
from .services.security import load_session

COOKIE = "hem_session"


@dataclass
class Auth:
    user: User
    session: Session

    @property
    def is_admin(self) -> bool:
        return self.user.role in ADMIN_ROLES

    @property
    def hh(self):
        return self.user.household_id


class Unauthorized(AppError):
    status = 401
    code = "unauthorized"


def current_auth(
    request: Request,
    db: DbSession = Depends(get_db),
    hem_session: str | None = Cookie(default=None),
    x_csrf_token: str | None = Header(default=None),
) -> Auth:
    res = load_session(db, hem_session)
    if not res:
        raise Unauthorized("Not authenticated")
    s, u = res
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not x_csrf_token or not hmac.compare_digest(x_csrf_token, s.csrf_token):
            raise Forbidden("CSRF token missing or invalid", code="csrf")
    return Auth(user=u, session=s)


def require(perm: str):
    def dep(auth: Auth = Depends(current_auth)) -> Auth:
        if not can(auth.user.role, perm):
            raise Forbidden("Permission denied", code="forbidden")
        return auth
    return dep
