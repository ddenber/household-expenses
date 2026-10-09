from concurrent.futures import ThreadPoolExecutor

from app.services import accounts as acc
from tests.conftest import Api, atm, bal_of, fund, jpeg_bytes, key


def wid(w, u):
    return acc.wallet_for(w.db, w.hh, u.id).id


def mk_expense(api, w, total="85", method="cash", supplier="Market", day="2026-03-05", cat="Ushqimore", user=None, submit=True, **kw):
    body = {"client_ref": key(), "category_id": str(w.cat[cat]), "supplier_name": supplier, "expense_date": day,
            "total": total, "payment_method": method, **kw}
    if user:
        body["user_id"] = str(user.id)
    r = api.post("/expenses", body)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    if submit:
        s = api.post(f"/expenses/{eid}/submit", {})
        assert s.status_code == 200, s.text
    return eid


def approve_post(admin, eid):
    assert admin.post(f"/expenses/{eid}/approve").status_code == 200
    r = admin.post(f"/expenses/{eid}/post")
    assert r.status_code == 200, r.text
    return r.json()


def test_cash_expense_reduces_wallet_only_after_posting(w, admin, ea):
    fund(admin, w)
    atm(admin, w, w.a, "500")
    eid = mk_expense(ea, w)
    assert bal_of(admin, wid(w, w.a)) == "500.00"
    admin.post(f"/expenses/{eid}/approve")
    assert bal_of(admin, wid(w, w.a)) == "500.00"  # approved is not posted
    admin.post(f"/expenses/{eid}/post")
    assert bal_of(admin, wid(w, w.a)) == "415.00"
    assert bal_of(admin, w.bank_id) == "1500.00"


def test_card_purchase_hits_bank_not_wallet(w, admin, eb):
    fund(admin, w)
    atm(admin, w, w.b, "400")
    eid = mk_expense(eb, w, "120", "card", "Elektro", cat="Elektronikë", bank_account_id=str(w.bank_id))
    approve_post(admin, eid)
    assert bal_of(admin, wid(w, w.b)) == "400.00"
    assert bal_of(admin, w.bank_id) == str("1480.00")


def test_bank_transfer_hits_bank_not_wallet(w, admin, eb):
    fund(admin, w)
    eid = mk_expense(eb, w, "50", "bank_transfer", "Furnizues", cat="Shërbime")
    approve_post(admin, eid)
    assert bal_of(admin, w.bank_id) == "1950.00"


def test_personal_funds_creates_payable_not_wallet_change(w, admin, ea):
    fund(admin, w)
    atm(admin, w, w.a, "100")
    eid = mk_expense(ea, w, "30", "personal_funds")
    approve_post(admin, eid)
    assert bal_of(admin, wid(w, w.a)) == "100.00"
    kp = {k["key"]: k["value"] for k in admin.get("/dashboard/admin").json()["kpis"]}
    assert kp["reimbursements_owed"] == "30.00"
    r = admin.post("/ledger/reimbursement", {"idempotency_key": key(), "date": "2026-03-10", "amount": "40", "bank_id": str(w.bank_id), "user_id": str(w.a.id)})
    assert r.status_code == 422
    r = admin.post("/ledger/reimbursement", {"idempotency_key": key(), "date": "2026-03-10", "amount": "30", "bank_id": str(w.bank_id), "user_id": str(w.a.id)})
    assert r.status_code == 201
    assert bal_of(admin, w.bank_id) == "1870.00"


def test_employee_cannot_approve_own_and_rejected_never_posts(w, admin, ea):
    fund(admin, w)
    atm(admin, w, w.a, "100")
    eid = mk_expense(ea, w, "10")
    assert ea.post(f"/expenses/{eid}/approve").status_code == 403
    assert admin.post(f"/expenses/{eid}/post").status_code == 409  # submitted, not approved
    assert admin.post(f"/expenses/{eid}/reject", {"reason": ""}).status_code == 422
    assert admin.post(f"/expenses/{eid}/reject", {"reason": "nuk lexohet"}).status_code == 200
    assert admin.post(f"/expenses/{eid}/post").status_code == 409
    assert admin.post(f"/expenses/{eid}/approve").status_code == 409
    assert bal_of(admin, wid(w, w.a)) == "100.00"
    assert admin.get(f"/ledger/transactions?expense_id={eid}").json() == []


def test_admin_cannot_approve_expense_they_own(w, admin):
    fund(admin, w)
    eid = mk_expense(admin, w, "10", "card", bank_account_id=str(w.bank_id))
    assert admin.post(f"/expenses/{eid}/approve").status_code == 403


def test_invalid_transitions(w, admin, ea):
    eid = mk_expense(ea, w, submit=False)
    assert admin.post(f"/expenses/{eid}/approve").status_code == 409  # draft
    assert admin.post(f"/expenses/{eid}/post").status_code == 409
    assert admin.post(f"/expenses/{eid}/reverse", {"reason": "x"}).status_code == 409


def test_double_post_fails_safely_and_concurrent_post_once(w, admin, ea):
    fund(admin, w)
    atm(admin, w, w.a, "300")
    eid = mk_expense(ea, w, "100")
    admin.post(f"/expenses/{eid}/approve")

    def go(_):
        return Api("admin@t.l").post(f"/expenses/{eid}/post").status_code
    with ThreadPoolExecutor(5) as ex:
        codes = list(ex.map(go, range(5)))
    assert codes.count(200) == 1 and codes.count(409) == 4
    assert bal_of(admin, wid(w, w.a)) == "200.00"
    assert len(admin.get(f"/ledger/transactions?expense_id={eid}").json()) == 1


def test_cash_expense_cannot_overdraw_wallet(w, admin, ea):
    fund(admin, w)
    atm(admin, w, w.a, "50")
    eid = mk_expense(ea, w, "80")
    admin.post(f"/expenses/{eid}/approve")
    r = admin.post(f"/expenses/{eid}/post")
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_funds"


def test_reversal_and_refund(w, admin, ea):
    fund(admin, w)
    atm(admin, w, w.a, "300")
    eid = mk_expense(ea, w, "100")
    approve_post(admin, eid)
    assert admin.post(f"/expenses/{eid}/refund", {"amount": "150"}).status_code == 422
    rf = admin.post(f"/expenses/{eid}/refund", {"amount": "40", "date": "2026-03-06"})
    assert rf.status_code == 201 and rf.json()["refund_of_id"] == eid
    rid = rf.json()["id"]
    approve_post(admin, rid)
    assert bal_of(admin, wid(w, w.a)) == "240.00"
    assert admin.post(f"/expenses/{eid}/refund", {"amount": "61"}).status_code == 422
    assert admin.post(f"/expenses/{eid}/reverse", {"reason": "x"}).status_code == 409  # refunds first
    assert admin.post(f"/expenses/{rid}/reverse", {"reason": "mistake"}).status_code == 200
    assert admin.post(f"/expenses/{eid}/reverse", {"reason": "dup"}).status_code == 200
    assert bal_of(admin, wid(w, w.a)) == "300.00"
    assert admin.get(f"/expenses/{eid}").json()["status"] == "reversed"


def test_expense_input_validation(w, ea):
    base = {"category_id": str(w.cat["Ushqimore"]), "supplier_name": "x", "expense_date": "2026-03-05", "payment_method": "cash"}
    assert ea.post("/expenses", {**base, "total": "10.005"}).status_code == 422
    assert ea.post("/expenses", {**base, "total": "-5"}).status_code == 422
    assert ea.post("/expenses", {**base, "total": "abc"}).status_code == 422
    assert ea.post("/expenses", {**base, "total": "5", "expense_date": "2099-01-01"}).status_code == 422
    assert ea.post("/expenses", {**base, "total": "5", "payment_method": "crypto"}).status_code == 422


def test_create_is_idempotent_by_client_ref(w, ea):
    b = {"client_ref": "abc", "total": "5"}
    r1, r2 = ea.post("/expenses", b), ea.post("/expenses", b)
    assert r1.json()["id"] == r2.json()["id"] and r2.status_code == 200


def test_analytics_by_supplier_and_category_use_ledger(w, admin, ea, eb):
    fund(admin, w)
    atm(admin, w, w.a, "500")
    atm(admin, w, w.b, "400")
    approve_post(admin, mk_expense(ea, w, "85", supplier="Conad", cat="Ushqimore"))
    approve_post(admin, mk_expense(eb, w, "120", "card", "Conad", cat="Ushqimore", bank_account_id=str(w.bank_id)))
    approve_post(admin, mk_expense(ea, w, "40", supplier="Farmaci X", cat="Barnatore"))
    sup = {r["name"]: r["total"] for r in admin.get("/analytics/spend?group=supplier").json()}
    cat = {r["name"]: r["total"] for r in admin.get("/analytics/spend?group=category").json()}
    assert sup == {"Conad": "205.00", "Farmaci X": "40.00"}
    assert cat == {"Ushqimore": "205.00", "Barnatore": "40.00"}
