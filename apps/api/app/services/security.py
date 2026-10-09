import hashlib
import hmac
import logging
import secrets
import time
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..errors import AppError
from ..models import Session, User, now

log = logging.getLogger("hem.security")
_ph = PasswordHasher()
_DUMMY = _ph.hash("dummy-password-for-timing")


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str | None) -> bool:
    try:
        return _ph.verify(hashed or _DUMMY, pw) and hashed is not None
    except (VerificationError, InvalidHashError):
        return False


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def create_session(db: DbSession, user: User) -> tuple[str, Session]:
    token = secrets.token_urlsafe(32)
    s = Session(
        user_id=user.id, token_hash=sha256_hex(token), csrf_token=secrets.token_urlsafe(24),
        expires_at=now() + timedelta(hours=get_settings().session_hours),
    )
    db.add(s)
    db.flush()
    return token, s


def load_session(db: DbSession, token: str | None):
    if not token:
        return None
    s = db.scalar(select(Session).where(Session.token_hash == sha256_hex(token)))
    if not s or s.revoked_at or s.expires_at < now():
        return None
    u = db.get(User, s.user_id)
    if not u or not u.is_active:
        return None
    return s, u


class TooManyRequests(AppError):
    status = 429
    code = "rate_limited"


_mem: dict[str, tuple[int, float]] = {}
_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        import redis
        _redis = redis.Redis.from_url(get_settings().redis_url, socket_timeout=0.5)
    return _redis


def rate_limit(key: str, limit: int, window: int = 60) -> None:
    st = get_settings()
    if not st.rate_limit_enabled:
        return
    try:
        r = _get_redis()
        k = f"rl:{key}:{int(time.time() // window)}"
        n = r.incr(k)
        if n == 1:
            r.expire(k, window + 1)
    except Exception:
        log.warning("rate limit degraded to in-memory (redis unavailable)")
        bucket = f"{key}:{int(time.time() // window)}"
        n = _mem.get(bucket, (0, 0))[0] + 1
        _mem[bucket] = (n, time.time())
        if len(_mem) > 10000:
            _mem.clear()
    if n > limit:
        raise TooManyRequests("Too many requests", code="rate_limited")


def sign(value: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()
