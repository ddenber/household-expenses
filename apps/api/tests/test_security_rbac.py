from app.services import accounts as acc
from tests.conftest import Api, PW, atm, fund, jpeg_bytes, key
from tests.test_expenses import mk_expense


def upload(api, eid, data=None, name="r.jpg"):
    return api.post(f"/expenses/{eid}/documents", files={"file": (name, jpeg_bytes() if data is None else data, "image/jpeg")})


def test_employee_cannot_see_or_touch_other_employees_data(w, admin, ea, eb):
    eid = mk_expense(ea, w, "10", submit=False)
    d = upload(ea, eid).json()["document_id"]
    assert eb.get(f"/expenses/{eid}").status_code == 404
    assert eb.get(f"/documents/{d}/url").status_code == 404
    assert eb.patch(f"/expenses/{eid}", {"notes": "x"}).status_code == 404
    assert eb.post(f"/expenses/{eid}/submit", {}).status_code == 404
    assert upload(eb, eid).status_code == 404
    assert eb.get("/expenses").json()["total"] == 0
    assert eb.get(f"/reconciliation?year=2026&month=3&user_id={w.a.id}").status_code == 404
    assert ea.get(f"/documents/{d}/url").status_code == 200
    assert admin.get(f"/documents/{d}/url").status_code == 200


def test_employee_blocked_from_admin_endpoints(w, ea):
    for m, u in [("get", "/users"), ("get", "/dashboard/admin"), ("get", "/ledger/transactions"), ("get", "/audit"),
                 ("get", "/exports/expenses"), ("get", "/analytics/spend")]:
        assert getattr(ea, m)(u).status_code == 403, u
    assert ea.post("/ledger/funding", {"idempotency_key": "x", "date": "2026-03-01", "amount": "5", "bank_id": str(w.bank_id)}).status_code == 403
    assert ea.post("/categories", {"name": "x"}).status_code == 403
    assert ea.post("/users", {"email": "z@z.zz", "name": "z", "password": "x" * 12}).status_code == 403
    assert ea.post("/expenses", {"user_id": str(w.b.id), "total": "5"}).status_code == 403


def test_auditor_is_read_only(w, admin, auditor, ea):
    assert auditor.get("/ledger/transactions").status_code == 200
    assert auditor.get("/audit").status_code == 200
    assert auditor.post("/ledger/funding", {"idempotency_key": "x", "date": "2026-03-01", "amount": "5", "bank_id": str(w.bank_id)}).status_code == 403
    assert auditor.post("/expenses", {"total": "5"}).status_code == 403
    eid = mk_expense(ea, w, "5", submit=False)
    assert auditor.post(f"/expenses/{eid}/ocr/retry").status_code == 403


def test_financial_admin_cannot_create_privileged_users(w, admin):
    r = admin.post("/users", {"email": "new@t.l", "name": "n", "password": "long-enough-pw", "role": "super_admin"})
    assert r.status_code == 403
    r = admin.post("/users", {"email": "new@t.l", "name": "n", "password": "long-enough-pw", "role": "employee"})
    assert r.status_code == 201


def test_unauthenticated_and_csrf(w):
    import app.main
    from fastapi.testclient import TestClient
    c = TestClient(app.main.app)
    assert c.get("/api/v1/expenses").status_code == 401
    a = Api("a@t.l")
    r = a.c.post("/api/v1/expenses", json={"total": "5"})  # no CSRF header
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf"
    r = a.c.post("/api/v1/expenses", json={"total": "5"}, headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 403


def test_readiness_reports_database_failure(w, monkeypatch):
    import app.main
    from fastapi.testclient import TestClient

    client = TestClient(app.main.app)
    assert client.get("/api/ready").status_code == 200

    def unavailable():
        raise OSError("synthetic database outage")

    monkeypatch.setattr(app.main.engine, "connect", unavailable)
    response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_cookie_flags_and_logout(w):
    c = Api("a@t.l")
    r = c.c.post("/api/v1/auth/login", json={"email": "a@t.l", "password": PW})
    c.csrf = r.json()["csrf_token"]
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=lax" in sc
    assert c.post("/auth/logout").status_code == 200
    assert c.get("/auth/me").status_code == 401


def test_brute_force_lockout(w):
    from fastapi.testclient import TestClient
    import app.main
    c = TestClient(app.main.app)
    for _ in range(5):
        assert c.post("/api/v1/auth/login", json={"email": "a@t.l", "password": "wrong"}).status_code == 401
    r = c.post("/api/v1/auth/login", json={"email": "a@t.l", "password": PW})
    assert r.status_code == 429


def test_upload_validation(w, ea):
    eid = mk_expense(ea, w, "10", submit=False)
    assert upload(ea, eid, b"not an image at all", "x.jpg").status_code == 415
    assert upload(ea, eid, b"", "x.jpg").status_code == 422
    assert upload(ea, eid, b"\xff\xd8\xff garbage", "x.jpg").status_code == 415
    assert upload(ea, eid, b"MZ\x90\x00 exe", "x.jpg").status_code == 415
    from app.config import get_settings
    big = jpeg_bytes() + b"0" * (get_settings().max_upload_bytes + 10)
    assert upload(ea, eid, big).status_code == 413
    ok = upload(ea, eid)
    assert ok.status_code == 202
    dup = upload(ea, eid)
    assert dup.status_code == 200 and dup.json()["duplicate_upload"] is True
    assert len(ea.get(f"/expenses/{eid}").json()["documents"]) == 1


def test_signed_url_roundtrip_and_tamper(w, ea):
    eid = mk_expense(ea, w, "10", submit=False)
    d = upload(ea, eid).json()["document_id"]
    url = ea.get(f"/documents/{d}/url").json()["url"]
    from fastapi.testclient import TestClient
    import app.main
    anon = TestClient(app.main.app)
    assert anon.get(url).status_code == 200
    assert anon.get(url.replace("sig=", "sig=0")).status_code == 403
    assert anon.get(url.replace("exp=", "exp=1")).status_code == 403


def test_audit_log_records_key_actions_without_pii(w, admin, ea):
    fund(admin, w)
    atm(admin, w, w.a, "100")
    eid = mk_expense(ea, w, "10")
    admin.post(f"/expenses/{eid}/approve")
    admin.post(f"/expenses/{eid}/post")
    log = admin.get("/audit").json()
    actions = {r["action"] for r in log}
    assert {"ledger.funding", "ledger.atm_withdrawal", "expense.submit", "expense.approve", "expense.post"} <= actions
    assert "a@t.l" not in str(log)


def test_new_household_isolation(w, admin):
    from app.db import SessionLocal
    from app.models import Household, User
    from app.services.security import hash_password
    db = SessionLocal()
    h2 = Household(name="Other")
    db.add(h2)
    db.flush()
    db.add(User(household_id=h2.id, email="o@t.l", name="O", role="financial_admin", password_hash=hash_password(PW)))
    db.commit()
    other = Api("o@t.l")
    fund(admin, w)
    assert other.get("/ledger/transactions").json() == []
    assert other.post("/ledger/funding", {"idempotency_key": key(), "date": "2026-03-01", "amount": "5", "bank_id": str(w.bank_id)}).status_code == 422
    tid = admin.get("/ledger/transactions").json()[0]["id"]
    assert other.get(f"/ledger/transactions/{tid}").status_code == 404
