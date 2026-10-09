from app.services import accounts as acc
from tests.conftest import atm, bal_of, fund, key
from tests.test_expenses import approve_post, mk_expense

REC = "/reconciliation?year=2026&month=3"


def setup_march(w, admin, ea, eb):
    fund(admin, w, "2000", "2026-03-01")
    atm(admin, w, w.a, "500", day="2026-03-02")
    atm(admin, w, w.b, "400", day="2026-03-02")
    approve_post(admin, mk_expense(ea, w, "85", supplier="Conad", day="2026-03-05"))
    approve_post(admin, mk_expense(eb, w, "120", "card", "Elektro", cat="Elektronikë", day="2026-03-06", bank_account_id=str(w.bank_id)))
    approve_post(admin, mk_expense(admin, w, "100", supplier="Pastrim", cat="Shërbime", day="2026-03-07", user=w.a))


def test_expected_cash_and_discrepancy(w, admin, ea, eb):
    setup_march(w, admin, ea, eb)
    a = admin.get(f"{REC}&user_id={w.a.id}").json()
    assert (a["opening"], a["withdrawals"], a["cash_expenses"], a["expected_closing"]) == ("0.00", "500.00", "185.00", "315.00")
    assert a["consistent"] is True
    b = admin.get(f"{REC}&user_id={w.b.id}").json()
    assert (b["cash_expenses"], b["expected_closing"]) == ("0.00", "400.00")  # card purchase untouched wallet
    assert ea.post("/reconciliation/declare", {"year": 2026, "month": 3, "amount": "310"}).json()["difference"] == "-5.00"
    assert admin.post("/reconciliation/declare", {"user_id": str(w.b.id), "year": 2026, "month": 3, "amount": "400"}).json()["difference"] == "0.00"


def test_pending_rejected_missing_reported_separately(w, admin, ea, eb):
    setup_march(w, admin, ea, eb)
    mk_expense(ea, w, "11", day="2026-03-10")
    rej = mk_expense(ea, w, "22", day="2026-03-11")
    admin.post(f"/expenses/{rej}/reject", {"reason": "x"})
    appr = mk_expense(ea, w, "33", day="2026-03-12")
    admin.post(f"/expenses/{appr}/approve")
    a = admin.get(f"{REC}&user_id={w.a.id}").json()
    assert a["pending"]["amount"] == "11.00" and a["rejected"]["amount"] == "22.00" and a["approved_not_posted"]["amount"] == "33.00"
    assert a["expected_closing"] == "315.00"  # none of them in expected
    assert a["missing_receipts"] == 4  # no documents attached in this test


def test_close_period_with_suspense_and_closed_period_rejects_edits(w, admin, ea, eb):
    setup_march(w, admin, ea, eb)
    assert admin.post("/reconciliation/close", {"user_id": str(w.a.id), "year": 2026, "month": 3}).status_code == 422  # no count
    ea.post("/reconciliation/declare", {"year": 2026, "month": 3, "amount": "310"})
    assert admin.post("/reconciliation/close", {"user_id": str(w.a.id), "year": 2026, "month": 3}).status_code == 422  # needs note/post
    r = admin.post("/reconciliation/close", {"user_id": str(w.a.id), "year": 2026, "month": 3, "post_difference": True})
    assert r.status_code == 200 and r.json()["status"] == "closed"
    wid = acc.wallet_for(w.db, w.hh, w.a.id).id
    assert bal_of(admin, wid) == "310.00"
    susp = acc.system_account(w.db, w.hh, "suspense").id
    assert bal_of(admin, susp) == "5.00"
    # employee can no longer change the declaration, and nothing can be posted into the closed month
    assert ea.post("/reconciliation/declare", {"year": 2026, "month": 3, "amount": "315"}).status_code == 409
    late = mk_expense(ea, w, "10", day="2026-03-20")
    admin.post(f"/expenses/{late}/approve")
    p = admin.post(f"/expenses/{late}/post")
    assert p.status_code == 409 and p.json()["error"]["code"] == "period_closed"
    tid = next(t["id"] for t in admin.get("/ledger/transactions?type=atm_withdrawal").json() if any(l["account_id"] == str(wid) for l in t["lines"]))
    admin.post(f"/ledger/transactions/{tid}/reverse", {"reason": "x"})  # reversal dated today (April+), allowed
    # but posting directly into the closed March wallet is blocked at ledger level
    r = admin.post("/ledger/employee-transfer", {"idempotency_key": key(), "date": "2026-03-25", "amount": "1", "from_user_id": str(w.a.id), "to_user_id": str(w.b.id)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "period_closed"
    # carry-forward: April opening == March closing from the ledger
    b = admin.get(f"{REC}&user_id={w.a.id}").json()
    assert b["difference"] == "-5.00" and b["count_adjustment"] == "-5.00" and b["consistent"] is True


def test_reopen_requires_reason_is_audited_and_reverses_difference(w, admin, ea, eb):
    setup_march(w, admin, ea, eb)
    ea.post("/reconciliation/declare", {"year": 2026, "month": 3, "amount": "310"})
    admin.post("/reconciliation/close", {"user_id": str(w.a.id), "year": 2026, "month": 3, "post_difference": True})
    body = {"user_id": str(w.a.id), "year": 2026, "month": 3}
    assert admin.post("/reconciliation/reopen", {**body, "reason": ""}).status_code == 422
    assert ea.post("/reconciliation/reopen", {**body, "reason": "x"}).status_code == 403
    assert admin.post("/reconciliation/reopen", {**body, "reason": "numarim i gabuar"}).json()["status"] == "open"
    wid = acc.wallet_for(w.db, w.hh, w.a.id).id
    assert bal_of(admin, wid) == "315.00"
    assert bal_of(admin, acc.system_account(w.db, w.hh, "suspense").id) == "0.00"
    assert any(r["action"] == "reconciliation.reopen" for r in admin.get("/audit").json())
    r = admin.post("/reconciliation/close", {**body, "post_difference": True})
    assert r.status_code == 200 and bal_of(admin, wid) == "310.00"


def test_carry_forward_opening_balance(w, admin, ea, eb):
    setup_march(w, admin, ea, eb)
    apr = admin.get(f"/reconciliation?year=2026&month=4&user_id={w.a.id}").json()
    assert apr["opening"] == "315.00" and apr["expected_closing"] == "315.00"


def test_employee_sees_only_own_reconciliation_and_statement_pdf(w, admin, ea, eb):
    setup_march(w, admin, ea, eb)
    assert ea.get(REC).json()["user_id"] == str(w.a.id)
    r = ea.get(f"{REC.replace('reconciliation', 'reconciliation/statement.pdf')}")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    assert eb.get(f"/reconciliation/statement.pdf?year=2026&month=3&user_id={w.a.id}").status_code == 404


def test_exports_csv_xlsx(w, admin, ea, eb):
    setup_march(w, admin, ea, eb)
    r = admin.get("/exports/expenses?format=csv")
    assert r.status_code == 200 and "Conad" in r.text and r.text.count("\n") >= 4
    r = admin.get("/exports/transactions?format=xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert "text/csv" in admin.get("/exports/transactions").headers["content-type"]
