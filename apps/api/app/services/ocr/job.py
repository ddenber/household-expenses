"""OCR job. Suggests field values only. It has NO access to the ledger."""
import logging
from datetime import date

from sqlalchemy import select

from ...config import get_settings
from ...db import SessionLocal
from ...models import Document, Expense, OcrResult
from ..audit import audit
from ..expenses import transition
from ..storage import get_storage
from . import extractor
from .providers import get_provider

log = logging.getLogger("hem.ocr")


def enqueue_ocr(document_id) -> None:
    st = get_settings()
    if st.ocr_inline:
        process_document(str(document_id))
        return
    try:
        import redis
        from rq import Queue
        Queue("ocr", connection=redis.Redis.from_url(st.redis_url)).enqueue(
            "app.services.ocr.job.process_document", str(document_id), job_timeout=300, retry=None)
    except Exception:
        log.exception("could not enqueue OCR job doc=%s", document_id)


def process_document(document_id: str) -> None:
    st = get_settings()
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if not doc:
            return
        e = db.scalar(select(Expense).where(Expense.id == doc.expense_id).with_for_update())
        if e.status == "uploaded":
            transition(db, e, "processing", None)
        doc.ocr_status = "processing"
        db.commit()

        provider = get_provider()
        result = OcrResult(document_id=doc.id, expense_id=doc.expense_id, provider=provider.name if provider else "none",
                           provider_real=bool(provider and provider.real), status="done")
        if provider is None:
            result.status = "skipped"
        else:
            try:
                out = provider.extract_text(get_storage().get(doc.storage_key), doc.mime)
                result.raw_text = out.text
                ext = out.fields or extractor.extract(out.text, out.confidence)
                extractor.validate(ext)
                result.extraction = ext
                result.confidence = {k: v["confidence"] for k, v in ext.items() if isinstance(v, dict)}
            except Exception as ex:  # a failed OCR never deletes the document
                result.status, result.error = "failed", f"{type(ex).__name__}: {str(ex)[:300]}"
                log.warning("ocr failed doc=%s err=%s", doc.id, type(ex).__name__)
        db.add(result)
        doc.ocr_status = result.status
        db.flush()

        e = db.scalar(select(Expense).where(Expense.id == doc.expense_id).with_for_update())
        if result.status == "done" and e.status in ("processing", "uploaded"):
            _suggest(e, result.extraction, st.ocr_confidence_threshold)
        db.refresh(e, ["documents"])
        if e.status == "processing" and all(d.ocr_status in ("done", "failed", "skipped") for d in e.documents):
            transition(db, e, "needs_review", None, "ocr finished")
        elif e.status == "uploaded" and result.status == "skipped":
            transition(db, e, "needs_review", None, "ocr skipped")
        audit(db, household_id=e.household_id, actor_id=None, action="ocr.finished", entity_type="document",
              entity_id=doc.id, details={"status": result.status, "provider": result.provider})
        db.commit()
    except Exception:
        db.rollback()
        log.exception("ocr job crashed doc=%s", document_id)
        raise
    finally:
        db.close()


def _suggest(e: Expense, ext: dict, threshold: float) -> None:
    from ..expenses import _supplier  # noqa
    needs = False
    if ext["supplier"]["value"] and not e.supplier_name:
        e.supplier_name = ext["supplier"]["value"]
        needs |= ext["supplier"]["confidence"] < threshold
    if ext["date"]["value"] and not e.expense_date:
        e.expense_date = date.fromisoformat(ext["date"]["value"])
        needs |= ext["date"]["confidence"] < threshold
    if ext["total"]["value"] and e.total is None:
        from decimal import Decimal
        e.total = Decimal(ext["total"]["value"])
        needs |= ext["total"]["confidence"] < threshold
    if e.total is None or not e.expense_date:
        needs = True  # missing fields: human must fill in
    if needs:
        e.ocr_needs_confirmation = True
