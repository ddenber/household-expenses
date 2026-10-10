import os

from app.services.ocr import extractor
from app.services.ocr.extractor import parse_amount, validate
from tests.conftest import jpeg_bytes
from tests.test_expenses import mk_expense
from tests.test_security_rbac import upload


def test_parse_amount_formats():
    from decimal import Decimal
    assert parse_amount("1.234,56") == Decimal("1234.56")
    assert parse_amount("1,234.56") == Decimal("1234.56")
    assert parse_amount("12,50") == Decimal("12.50")
    assert parse_amount("12") is None


def test_extractor_finds_fields_and_validates_schema():
    t = "SUPERMARKET KONAD\nData: 05/03/2026\nQumesht 2,50\nSUBTOTAL 10.00\nTVSH 2.00\nTOTAL 12,00 EUR"
    r = extractor.extract(t, 0.9)
    assert r["total"]["value"] == "12.00" and r["date"]["value"] == "2026-03-05" and r["currency"]["value"] == "EUR"
    assert r["supplier"]["value"] == "SUPERMARKET KONAD"
    validate(r)


def test_supplier_skips_noise_lines():
    t = "FATURË FISKALE\nNIPT: 81234567\nTel: 044 123 456\nBIM MARKET SH.P.K.\n05/03/2026\nTOTALI 7.40 EUR"
    r = extractor.extract(t, 0.9)
    assert r["supplier"]["value"] == "BIM MARKET SH.P.K" and r["total"]["value"] == "7.40"


def test_extractor_never_invents_total():
    r = extractor.extract("Dyqan\n12/03/2026\nQumesht 2.50\nBukë 1.20\n", 0.9)
    assert r["total"]["value"] is None and r["total"]["confidence"] == 0


def test_conflicting_totals_get_low_confidence():
    r = extractor.extract("X Shop\n01/02/2026\nTOTAL 10.00\nTOTAL 12.00", 0.9)
    assert r["total"]["confidence"] < 0.8


def test_upload_returns_immediately_then_ocr_marks_simulated_and_needs_review(w, ea):
    r = ea.post("/expenses", {"client_ref": "c1"})
    eid = r.json()["id"]
    up = upload(ea, eid)
    assert up.status_code == 202
    e = ea.get(f"/expenses/{eid}").json()
    assert e["status"] == "needs_review"  # inline OCR in tests
    assert e["ocr"][0]["provider"] == "simulated" and e["ocr"][0]["provider_real"] is False
    assert e["total"] == "12.50" and e["ocr_needs_confirmation"] is True
    assert e["ocr"][0]["extraction"]["schema_version"] == "v1"


def test_low_confidence_requires_confirmation_and_corrections_are_stored(w, ea):
    eid = ea.post("/expenses", {"client_ref": "c2"}).json()["id"]
    upload(ea, eid)
    ea.patch(f"/expenses/{eid}", {"category_id": str(w.cat["Ushqimore"]), "total": "13.00"})
    s = ea.post(f"/expenses/{eid}/submit", {})
    assert s.status_code == 422 and s.json()["error"]["code"] == "needs_confirmation"
    assert ea.post(f"/expenses/{eid}/submit", {"confirm_low_confidence": True}).json()["status"] == "submitted"
    from app.db import SessionLocal
    from app.models import OcrCorrection
    db = SessionLocal()
    c = db.query(OcrCorrection).all()
    assert [(x.field, x.old_value, x.new_value) for x in c] == [("total", "12.50", "13.00")]


def test_correction_uses_latest_successful_ocr_result(w, ea):
    from datetime import datetime, timedelta, timezone
    from uuid import UUID

    from app.db import SessionLocal
    from app.models import OcrCorrection, OcrResult

    eid = ea.post("/expenses", {"client_ref": "latest-ocr"}).json()["id"]
    document_id = upload(ea, eid).json()["document_id"]
    with SessionLocal() as db:
        db.add(OcrResult(
            document_id=UUID(document_id), expense_id=UUID(eid), provider="simulated",
            provider_real=False, status="done", extraction={"total": {"value": "14.00"}},
            created_at=datetime.now(timezone.utc) + timedelta(seconds=1),
        ))
        db.commit()

    assert ea.patch(f"/expenses/{eid}", {"total": "15.00"}).status_code == 200
    with SessionLocal() as db:
        corrections = db.query(OcrCorrection).filter_by(expense_id=UUID(eid), field="total").all()
        assert [(c.old_value, c.new_value) for c in corrections] == [("14.00", "15.00")]


def test_failed_ocr_keeps_document_and_allows_manual_entry(w, ea, monkeypatch):
    from app.services.ocr import providers

    class Boom(providers.OcrProvider):
        name, real = "boom", True

        def extract_text(self, data, mime):
            raise RuntimeError("engine crashed")
    monkeypatch.setattr("app.services.ocr.job.get_provider", lambda: Boom())
    eid = ea.post("/expenses", {"client_ref": "c3"}).json()["id"]
    assert upload(ea, eid).status_code == 202
    e = ea.get(f"/expenses/{eid}").json()
    assert e["status"] == "needs_review" and len(e["documents"]) == 1
    assert e["ocr"][0]["status"] == "failed" and "engine crashed" in e["ocr"][0]["error"]
    assert e["total"] is None


def test_real_tesseract_reads_a_rendered_receipt(w, ea, monkeypatch):
    import shutil
    import pytest
    if not shutil.which("tesseract"):
        pytest.skip("tesseract not installed")
    from PIL import Image, ImageDraw, ImageFont
    import io
    img = Image.new("RGB", (900, 500), "white")
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except OSError:
        pytest.skip("no font")
    for i, line in enumerate(["CONAD MARKET", "Data: 05/03/2026", "Qumesht 2.50", "TOTAL 12.50 EUR"]):
        d.text((30, 30 + i * 80), line, fill="black", font=f)
    b = io.BytesIO()
    img.save(b, "PNG")
    monkeypatch.setenv("OCR_PROVIDER", "tesseract")
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "ocr_provider", "tesseract")
    eid = ea.post("/expenses", {"client_ref": "c4"}).json()["id"]
    ea.post(f"/expenses/{eid}/documents", files={"file": ("r.png", b.getvalue(), "image/png")})
    e = ea.get(f"/expenses/{eid}").json()
    assert e["ocr"][0]["provider"] == "tesseract" and e["ocr"][0]["provider_real"] is True
    assert e["total"] == "12.50" and e["expense_date"] == "2026-03-05"


def test_ocr_module_has_no_ledger_access():
    import pathlib
    for p in pathlib.Path("app/services/ocr").glob("*.py"):
        src = p.read_text()
        assert "import" not in "".join(l for l in src.splitlines() if "ledger" in l or "post_transaction" in l), p
        assert "services.ledger" not in src and "post_transaction" not in src, p
