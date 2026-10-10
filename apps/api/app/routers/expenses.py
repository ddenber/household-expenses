import time
import uuid
from datetime import date
import datetime as dt

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import Auth, current_auth, require
from ..errors import Forbidden, Invalid, NotFound
from ..models import Document, Expense, ExpenseStatusHistory, OcrResult
from ..money import fmt
from ..rbac import ADMIN_ROLES, can
from ..services import documents as docs
from ..services import expenses as svc
from ..services.audit import audit
from ..services.ocr.job import enqueue_ocr
from ..services.security import rate_limit, sign
from ..services.storage import EXT_MIME, get_storage

router = APIRouter(tags=["expenses"])


class ExpenseIn(BaseModel):
    client_ref: str | None = None
    user_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    supplier_name: str | None = None
    expense_date: date | None = None
    total: str | int | None = None
    payment_method: str | None = None
    notes: str | None = None
    bank_account_id: uuid.UUID | None = None


class ExpensePatch(BaseModel):
    category_id: uuid.UUID | None = None
    supplier_name: str | None = None
    expense_date: date | None = None
    total: str | int | None = None
    payment_method: str | None = None
    notes: str | None = None
    bank_account_id: uuid.UUID | None = None


class SubmitIn(BaseModel):
    confirm_low_confidence: bool = False


class ReasonIn(BaseModel):
    reason: str


class RefundIn(BaseModel):
    amount: str | int
    date: dt.date | None = None
    notes: str | None = None


@router.post("/expenses", status_code=201)
def create(body: ExpenseIn, response: Response, auth: Auth = Depends(require("expense.create_own")), db: Session = Depends(get_db)):
    e, replayed = svc.create_expense(db, auth, body.model_dump(exclude_unset=True))
    if not replayed:
        audit(db, household_id=auth.hh, actor_id=auth.user.id, action="expense.create", entity_type="expense", entity_id=e.id)
    db.commit()
    response.status_code = 200 if replayed else 201
    return svc.serialize(e)


@router.get("/expenses")
def list_expenses(
    auth: Auth = Depends(current_auth), db: Session = Depends(get_db), status: str | None = None,
    user_id: uuid.UUID | None = None, category_id: uuid.UUID | None = None, supplier: str | None = None,
    payment_method: str | None = None, date_from: date | None = None, date_to: date | None = None,
    q: str | None = None, limit: int = Query(100, le=500), offset: int = 0,
):
    stmt = select(Expense).where(Expense.household_id == auth.hh)
    if auth.user.role == "employee":
        stmt = stmt.where(Expense.user_id == auth.user.id)
    elif user_id:
        stmt = stmt.where(Expense.user_id == user_id)
    if status:
        stmt = stmt.where(Expense.status.in_(status.split(",")))
    if category_id:
        stmt = stmt.where(Expense.category_id == category_id)
    if payment_method:
        stmt = stmt.where(Expense.payment_method == payment_method)
    if supplier:
        stmt = stmt.where(Expense.supplier_name.ilike(f"%{supplier}%"))
    if date_from:
        stmt = stmt.where(Expense.expense_date >= date_from)
    if date_to:
        stmt = stmt.where(Expense.expense_date <= date_to)
    if q:
        stmt = stmt.where(or_(Expense.supplier_name.ilike(f"%{q}%"), Expense.notes.ilike(f"%{q}%")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Expense.created_at.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": [svc.serialize(e) for e in rows]}


@router.get("/expenses/{eid}")
def get_one(eid: uuid.UUID, auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    e = svc.get_expense(db, auth, eid)
    out = svc.serialize(e)
    out["documents"] = [{"id": str(d.id), "page_no": d.page_no, "mime": d.mime, "size": d.size, "ocr_status": d.ocr_status,
                         "filename": d.filename} for d in e.documents]
    ocr = db.scalars(select(OcrResult).where(OcrResult.expense_id == e.id).order_by(OcrResult.created_at)).all()
    out["ocr"] = [{"document_id": str(r.document_id), "provider": r.provider, "provider_real": r.provider_real,
                   "schema_version": r.schema_version, "status": r.status, "error": r.error, "extraction": r.extraction,
                   "confidence": r.confidence} for r in ocr]
    out["history"] = [{"from": h.from_status, "to": h.to_status, "at": h.at.isoformat(), "note": h.note}
                      for h in db.scalars(select(ExpenseStatusHistory).where(ExpenseStatusHistory.expense_id == e.id).order_by(ExpenseStatusHistory.at))]
    out["refunded_total"] = fmt(svc.refunded_total(db, e.id)) if e.status == "posted" else None
    return out


@router.patch("/expenses/{eid}")
def patch(eid: uuid.UUID, body: ExpensePatch, auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    if auth.user.role not in ADMIN_ROLES and auth.user.role != "employee":
        raise Forbidden("Read-only role")
    e = svc.get_expense(db, auth, eid, for_update=True)
    svc.update_expense(db, auth, e, body.model_dump(exclude_unset=True))
    db.commit()
    return svc.serialize(e)


@router.post("/expenses/{eid}/documents", status_code=202)
async def upload(eid: uuid.UUID, response: Response, file: UploadFile = File(...), auth: Auth = Depends(require("expense.create_own")),
                 db: Session = Depends(get_db)):
    rate_limit(f"upload:{auth.user.id}", 60)
    e = svc.get_expense(db, auth, eid, for_update=True)
    data = await file.read(get_settings().max_upload_bytes + 1)
    d, dup = docs.add_document(db, auth, e, file.filename or "receipt", data)
    warn = None if dup else docs.duplicate_warning(db, d)
    db.commit()
    if not dup:
        enqueue_ocr(d.id)
    else:
        response.status_code = 200
    return {"document_id": str(d.id), "page_no": d.page_no, "duplicate_upload": dup, "possible_duplicate_of_expense": warn,
            "ocr_status": d.ocr_status, "expense_status": e.status}


@router.post("/expenses/{eid}/ocr/retry", status_code=202)
def ocr_retry(eid: uuid.UUID, auth: Auth = Depends(require("expense.create_own")), db: Session = Depends(get_db)):
    e = svc.get_expense(db, auth, eid)
    if e.status not in svc.EDITABLE:
        raise Invalid("Not editable", code="not_editable")
    ids = [d.id for d in e.documents if d.ocr_status in ("failed", "skipped", "pending")]
    for did in ids:
        enqueue_ocr(did)
    return {"queued": len(ids)}


@router.post("/expenses/{eid}/submit")
def submit(eid: uuid.UUID, body: SubmitIn, auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    if auth.user.role == "auditor":
        raise Forbidden("Read-only role")
    e = svc.get_expense(db, auth, eid, for_update=True)
    svc.submit(db, auth, e, body.confirm_low_confidence)
    db.commit()
    return svc.serialize(e)


def _admin_action(fn):
    def handler(eid: uuid.UUID, auth: Auth, db: Session, **kw):
        e = svc.get_expense(db, auth, eid, for_update=True)
        fn(db, auth, e, **kw)
        db.commit()
        return svc.serialize(e)
    return handler


@router.post("/expenses/{eid}/approve")
def approve(eid: uuid.UUID, auth: Auth = Depends(require("expense.approve")), db: Session = Depends(get_db)):
    return _admin_action(svc.approve)(eid, auth, db)


@router.post("/expenses/{eid}/reject")
def reject(eid: uuid.UUID, body: ReasonIn, auth: Auth = Depends(require("expense.approve")), db: Session = Depends(get_db)):
    return _admin_action(svc.reject)(eid, auth, db, reason=body.reason)


@router.post("/expenses/{eid}/return")
def return_(eid: uuid.UUID, body: ReasonIn, auth: Auth = Depends(require("expense.approve")), db: Session = Depends(get_db)):
    return _admin_action(svc.return_for_correction)(eid, auth, db, reason=body.reason)


@router.post("/expenses/{eid}/reopen")
def reopen(eid: uuid.UUID, auth: Auth = Depends(require("expense.create_own")), db: Session = Depends(get_db)):
    return _admin_action(svc.reopen_rejected)(eid, auth, db)


@router.post("/expenses/{eid}/post")
def post(eid: uuid.UUID, auth: Auth = Depends(require("expense.post")), db: Session = Depends(get_db)):
    e, txn = svc.post(db, auth, eid)
    db.commit()
    return {**svc.serialize(e), "transaction_id": str(txn.id)}


@router.post("/expenses/{eid}/reverse")
def reverse(eid: uuid.UUID, body: ReasonIn, auth: Auth = Depends(require("expense.post")), db: Session = Depends(get_db)):
    e = svc.reverse(db, auth, eid, body.reason)
    db.commit()
    return svc.serialize(e)


@router.post("/expenses/{eid}/refund", status_code=201)
def refund(eid: uuid.UUID, body: RefundIn, auth: Auth = Depends(require("expense.post")), db: Session = Depends(get_db)):
    r = svc.create_refund(db, auth, eid, body.amount, body.notes, body.date)
    db.commit()
    return svc.serialize(r)


def _doc_for(db, auth, did) -> Document:
    d = db.get(Document, did)
    if not d or d.household_id != auth.hh:
        raise NotFound("Document not found")
    if auth.user.role == "employee" and d.owner_user_id != auth.user.id:
        raise NotFound("Document not found")
    if not can(auth.user.role, "document.read_all") and d.owner_user_id != auth.user.id:
        raise NotFound("Document not found")
    return d


@router.get("/documents/{did}/url")
def doc_url(did: uuid.UUID, auth: Auth = Depends(current_auth), db: Session = Depends(get_db)):
    d = _doc_for(db, auth, did)
    audit(db, household_id=auth.hh, actor_id=auth.user.id, action="document.access", entity_type="document", entity_id=d.id)
    db.commit()
    return {"url": get_storage().signed_url(d.storage_key), "expires_in": get_settings().signed_url_seconds, "mime": d.mime}


@router.get("/files")
def serve_file(k: str, exp: int, sig: str):
    import hmac
    if exp < time.time() or not hmac.compare_digest(sig, sign(f"{k}:{exp}")):
        raise Forbidden("Link expired or invalid", code="bad_signature")
    try:
        data = get_storage().get(k)
    except Exception:
        raise NotFound("File not found")
    mime = EXT_MIME.get(k.rsplit(".", 1)[-1], "application/octet-stream")
    return Response(content=data, media_type=mime, headers={"Cache-Control": "private, no-store", "Content-Disposition": "inline"})
