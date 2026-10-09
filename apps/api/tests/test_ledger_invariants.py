from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import SessionLocal, engine
from app.errors import Conflict, Invalid
from app.services import accounts as acc
from app.services.ledger import Line, post_transaction, reverse_transaction
from tests.conftest import atm, bal_of, fund, key
from datetime import date


def wallet_id(w, user):
    return acc.wallet_for(w.db, w.hh, user.id).id


def test_atm_withdrawal_is_not_an_expense_and_moves_bank_to_wallet(w, admin):
    fund(admin, w, "2000")
    atm(admin, w, w.a, "500")
    assert bal_of(admin, w.bank_id) == "1500.00"
    assert bal_of(admin, wallet_id(w, w.a)) == "500.00"
    assert bal_of(admin, wallet_id(w, w.b)) == "0.00"
    kpis = {k["key"]: k for k in admin.get("/dashboard/admin").json()["kpis"]}
    assert kpis["total_expenses_net"]["value"] == "0.00"
    assert kpis["month_expenses"]["value"] == "0.00"


def test_atm_fee_is_separate_bank_fee_expense(w, admin):
    fund(admin, w, "1000")
    r = atm(admin, w, w.a, "300", fee="2.50").json()
    assert r["fee_transaction"]["type"] == "bank_fee"
    assert bal_of(admin, w.bank_id) == "697.50"
    assert bal_of(admin, wallet_id(w, w.a)) == "300.00"
    kp = {k["key"]: k["value"] for k in admin.get("/dashboard/admin").json()["kpis"]}
    assert kp["bank_fees"] == "2.50"


def test_every_transaction_is_balanced_and_decimal_exact(w, admin):
    fund(admin, w, "1000.10")
    atm(admin, w, w.a, "0.10")
    atm(admin, w, w.b, "0.20", fee="0.01")
    rows = w.db.execute(text("select transaction_id, sum(debit), sum(credit), sum(base_debit), sum(base_credit) from journal_lines group by 1")).all()
    assert rows
    for _, d, c, bd, bc in rows:
        assert d == c and bd == bc
    assert bal_of(admin, w.bank_id) == "999.79"


def test_rejects_unbalanced_and_bad_lines(w):
    db = SessionLocal()
    wl, bk = wallet_id(w, w.a), w.bank_id
    with pytest.raises(Invalid):
        post_transaction(db, household_id=w.hh, type="x", lines=[Line(wl, debit=Decimal("5")), Line(bk, credit=Decimal("4"))], key="k1", occurred_at=date(2026, 3, 1))
    with pytest.raises(Invalid):
        post_transaction(db, household_id=w.hh, type="x", lines=[Line(wl, debit=Decimal("5"))], key="k2", occurred_at=date(2026, 3, 1))
    with pytest.raises(Invalid):
        post_transaction(db, household_id=w.hh, type="x", lines=[Line(wl, debit=Decimal("5.001")), Line(bk, credit=Decimal("5.001"))], key="k3", occurred_at=date(2026, 3, 1))
    with pytest.raises(Invalid):
        post_transaction(db, household_id=w.hh, type="x", lines=[Line(wl, debit=Decimal("0")), Line(bk, credit=Decimal("0"))], key="k4", occurred_at=date(2026, 3, 1))


def test_db_rejects_unbalanced_even_if_app_bypassed(w):
    from app.models import FinancialTransaction, JournalLine
    db = SessionLocal()
    t = FinancialTransaction(household_id=w.hh, type="x", occurred_at=date(2026, 3, 1), idempotency_key="raw", payload_hash="h")
    db.add(t)
    db.flush()
    db.add(JournalLine(transaction_id=t.id, account_id=w.bank_id, debit=Decimal("5"), base_debit=Decimal("5")))
    db.add(JournalLine(transaction_id=t.id, account_id=wallet_id(w, w.a), credit=Decimal("4"), base_credit=Decimal("4")))
    with pytest.raises(DBAPIError):
        db.commit()


def test_posted_lines_and_transactions_are_immutable_in_db(w, admin):
    fund(admin, w)
    with pytest.raises(DBAPIError):
        with engine.begin() as c:
            c.execute(text("update journal_lines set debit = debit + 1"))
    with pytest.raises(DBAPIError):
        with engine.begin() as c:
            c.execute(text("delete from journal_lines"))
    with pytest.raises(DBAPIError):
        with engine.begin() as c:
            c.execute(text("update financial_transactions set description = 'tamper'"))
    with pytest.raises(DBAPIError):
        with engine.begin() as c:
            c.execute(text("delete from financial_transactions"))
    with pytest.raises(DBAPIError):
        with engine.begin() as c:
            c.execute(text("update audit_log set action = 'x'"))


def test_idempotent_posting_replays_and_conflicting_payload_fails(w, admin):
    body = {"idempotency_key": "same-key", "date": "2026-03-01", "amount": "100", "bank_id": str(w.bank_id)}
    r1 = admin.post("/ledger/funding", body)
    r2 = admin.post("/ledger/funding", body)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r2.json()["replayed"] is True and r1.json()["transaction"]["id"] == r2.json()["transaction"]["id"]
    assert bal_of(admin, w.bank_id) == "100.00"
    r3 = admin.post("/ledger/funding", {**body, "amount": "999"})
    assert r3.status_code == 409 and r3.json()["error"]["code"] == "idempotency_conflict"
    assert bal_of(admin, w.bank_id) == "100.00"


def test_concurrent_posting_same_key_posts_once(w, admin):
    def go(_):
        db = SessionLocal()
        try:
            t, replayed = post_transaction(db, household_id=w.hh, type="funding", key="race", occurred_at=date(2026, 3, 1),
                                           lines=[Line(w.bank_id, debit=Decimal("10")), Line(acc.system_account(db, w.hh, "owner_funding").id, credit=Decimal("10"))])
            db.commit()
            return replayed
        finally:
            db.close()
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(go, range(8)))
    assert res.count(False) == 1
    assert bal_of(admin, w.bank_id) == "10.00"


def test_concurrent_withdrawals_cannot_overdraw_bank(w, admin):
    fund(admin, w, "100")

    def go(i):
        a = __import__("tests.conftest", fromlist=["Api"]).Api("admin@t.l")
        return a.post("/ledger/atm-withdrawal", {"idempotency_key": f"w{i}", "date": "2026-03-02", "amount": "60",
                                                  "bank_id": str(w.bank_id), "user_id": str(w.a.id)}).status_code
    with ThreadPoolExecutor(4) as ex:
        codes = list(ex.map(go, range(4)))
    assert codes.count(201) == 1 and codes.count(409) == 3
    assert bal_of(admin, w.bank_id) == "40.00"


def test_insufficient_funds_blocks_return_and_transfer(w, admin):
    fund(admin, w, "100")
    atm(admin, w, w.a, "50")
    r = admin.post("/ledger/cash-return", {"idempotency_key": key(), "date": "2026-03-03", "amount": "80", "bank_id": str(w.bank_id), "user_id": str(w.a.id)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_funds"
    r = admin.post("/ledger/employee-transfer", {"idempotency_key": key(), "date": "2026-03-03", "amount": "20", "from_user_id": str(w.a.id), "to_user_id": str(w.b.id)})
    assert r.status_code == 201
    assert bal_of(admin, wallet_id(w, w.b)) == "20.00"
    r = admin.post("/ledger/cash-return", {"idempotency_key": key(), "date": "2026-03-03", "amount": "30", "bank_id": str(w.bank_id), "user_id": str(w.a.id)})
    assert r.status_code == 201
    assert bal_of(admin, w.bank_id) == "80.00"


def test_reversal_mirrors_and_can_only_happen_once(w, admin):
    fund(admin, w, "100")
    tid = admin.get("/ledger/transactions").json()[0]["id"]
    r = admin.post(f"/ledger/transactions/{tid}/reverse", {"reason": "typo"})
    assert r.status_code == 201
    assert bal_of(admin, w.bank_id) == "0.00"
    assert admin.post(f"/ledger/transactions/{tid}/reverse", {"reason": "again"}).status_code == 409
    rid = r.json()["transaction"]["id"]
    assert admin.post(f"/ledger/transactions/{rid}/reverse", {"reason": "x"}).status_code == 409
    assert admin.post(f"/ledger/transactions/{tid}/reverse", {"reason": ""}).status_code in (409, 422)


def test_non_eur_rejected(w):
    db = SessionLocal()
    with pytest.raises(Invalid):
        post_transaction(db, household_id=w.hh, type="x", currency="USD", key="u", occurred_at=date(2026, 3, 1),
                         lines=[Line(w.bank_id, debit=Decimal("1")), Line(wallet_id(w, w.a), credit=Decimal("1"))])
