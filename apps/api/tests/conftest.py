import os
import re
import tempfile

os.environ.update({
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://hem:hem_dev_pw@localhost:5432/hem_test"),
    "RATE_LIMIT_ENABLED": "false", "OCR_INLINE": "true", "OCR_PROVIDER": "simulated", "APP_ENV": "test",
    "LOCAL_STORAGE_DIR": tempfile.mkdtemp(prefix="hem-test-"), "STORAGE_BACKEND": "local",
})

import io  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Household, User  # noqa: E402
from app.services import accounts as acc  # noqa: E402
from app.services.security import hash_password  # noqa: E402

PW = "correct-horse-battery"


@pytest.fixture(scope="session", autouse=True)
def migrated():
    # This fixture destroys the public schema. Require an explicitly selected test DB.
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url or os.environ.get("HEM_ALLOW_TEST_DB_RESET") != "1":
        raise RuntimeError("Set TEST_DATABASE_URL and HEM_ALLOW_TEST_DB_RESET=1 for an isolated test database")
    from sqlalchemy.engine import make_url
    database = make_url(test_url).database or ""
    if not re.search(r"(^test_|_test$|_test_)", database):
        raise RuntimeError("TEST_DATABASE_URL database name must contain a test marker")
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini")), "head")


@pytest.fixture(autouse=True)
def clean(migrated):
    with engine.begin() as c:
        c.execute(text("select pg_terminate_backend(pid) from pg_stat_activity where datname = current_database() and pid <> pg_backend_pid() and state like 'idle in transaction%'"))
    with engine.begin() as c:
        tabs = c.execute(text("select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'")).scalars().all()
        c.execute(text("TRUNCATE " + ",".join(tabs) + " RESTART IDENTITY CASCADE"))
    yield


class World:
    """One household: admin, employees A and B, one bank account."""

    def __init__(self):
        db = SessionLocal()
        h = Household(name="Test")
        db.add(h)
        db.flush()
        acc.seed_default_categories(db, h.id)
        self.bank = acc.create_bank_account(db, h.id, "Banka")
        mk = lambda email, role, name: User(household_id=h.id, email=email, name=name, role=role, password_hash=hash_password(PW))
        self.admin, self.a, self.b, self.auditor = (mk("admin@t.l", "financial_admin", "Admin"), mk("a@t.l", "employee", "A"),
                                                     mk("b@t.l", "employee", "B"), mk("aud@t.l", "auditor", "Aud"))
        db.add_all([self.admin, self.a, self.b, self.auditor])
        db.flush()
        for e in (self.a, self.b):
            acc.wallet_for(db, h.id, e.id)
            acc.payable_for(db, h.id, e.id)
        self.hh = h.id
        self.cat = {c.name: c.id for c in db.scalars(__import__("sqlalchemy").select(__import__("app.models", fromlist=["Category"]).Category))}
        db.commit()
        self.db = db
        self.bank_id = self.bank.id
        for u in (self.admin, self.a, self.b, self.auditor):
            db.refresh(u)


class Api:
    def __init__(self, email):
        self.c = TestClient(app)
        r = self.c.post("/api/v1/auth/login", json={"email": email, "password": PW})
        assert r.status_code == 200, r.text
        self.csrf = r.json()["csrf_token"]

    def req(self, method, url, **kw):
        h = kw.pop("headers", {})
        h["X-CSRF-Token"] = self.csrf
        return self.c.request(method, "/api/v1" + url, headers=h, **kw)

    def get(self, url, **kw):
        return self.req("GET", url, **kw)

    def post(self, url, json=None, **kw):
        return self.req("POST", url, json=json, **kw)

    def patch(self, url, json=None, **kw):
        return self.req("PATCH", url, json=json, **kw)


def jpeg_bytes(color=(200, 200, 200), size=(40, 40)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "JPEG")
    return b.getvalue()


def key() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def w():
    return World()


@pytest.fixture
def admin(w):
    return Api("admin@t.l")


@pytest.fixture
def ea(w):
    return Api("a@t.l")


@pytest.fixture
def eb(w):
    return Api("b@t.l")


@pytest.fixture
def auditor(w):
    return Api("aud@t.l")


def fund(admin, w, amount="2000", day="2026-03-01"):
    r = admin.post("/ledger/funding", {"idempotency_key": key(), "date": day, "amount": amount, "bank_id": str(w.bank_id)})
    assert r.status_code == 201, r.text


def atm(admin, w, user, amount, fee=None, day="2026-03-02", k=None):
    r = admin.post("/ledger/atm-withdrawal", {"idempotency_key": k or key(), "date": day, "amount": amount, "bank_id": str(w.bank_id),
                                              "user_id": str(user.id), "fee": fee})
    assert r.status_code == 201, r.text
    return r


def balances(admin):
    return {a["name"]: a["balance"] for a in admin.get("/accounts").json()}


def bal_of(admin, account_id):
    return next(a["balance"] for a in admin.get("/accounts").json() if a["id"] == str(account_id))
