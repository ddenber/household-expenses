import hashlib
import io
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..errors import Conflict, Invalid
from ..models import Document, Expense
from .audit import audit
from .expenses import EDITABLE, transition
from .storage import get_storage

log = logging.getLogger("hem.documents")
ALLOWED = {"image/jpeg": "jpg", "image/png": "png", "image/heic": "heic", "application/pdf": "pdf"}


def sniff(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"heim", b"heis"):
        return "image/heic"
    return None


def validate_upload(data: bytes) -> str:
    st = get_settings()
    if not data:
        raise Invalid("Empty file", code="empty_file")
    if len(data) > st.max_upload_bytes:
        raise Invalid("File too large", code="file_too_large", status=413)
    mime = sniff(data)
    if not mime:
        raise Invalid("Unsupported file type", code="unsupported_type", status=415)
    try:
        if mime == "application/pdf":
            import fitz
            with fitz.open(stream=data, filetype="pdf") as d:
                if d.page_count < 1 or d.page_count > st.max_pdf_pages:
                    raise Invalid("PDF page count not allowed", code="pdf_pages")
        else:
            from PIL import Image
            if mime == "image/heic":
                import pillow_heif
                pillow_heif.register_heif_opener()
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
    except Invalid:
        raise
    except Exception:
        raise Invalid("File is corrupt or unreadable", code="corrupt_file", status=415)
    return mime


def add_document(db: Session, auth, e: Expense, filename: str, data: bytes) -> tuple[Document, bool]:
    if e.status not in EDITABLE:
        raise Conflict("Documents can no longer be added", code="not_editable")
    mime = validate_upload(data)
    sha = hashlib.sha256(data).hexdigest()
    dup = db.scalar(select(Document).where(Document.expense_id == e.id, Document.sha256 == sha))
    if dup:
        return dup, True
    page = len(e.documents) + 1
    key = f"{e.household_id}/{e.id}/{uuid.uuid4().hex}.{ALLOWED[mime]}"
    get_storage().put(key, data, mime)
    d = Document(household_id=e.household_id, expense_id=e.id, owner_user_id=e.user_id, page_no=page,
                 filename=(filename or "receipt")[:200], mime=mime, size=len(data), sha256=sha, storage_key=key)
    db.add(d)
    db.flush()
    db.refresh(e, ["documents"])
    if e.status == "draft":
        transition(db, e, "uploaded", auth.user.id)
    audit(db, household_id=e.household_id, actor_id=auth.user.id, action="document.upload", entity_type="document",
          entity_id=d.id, details={"expense_id": str(e.id), "size": len(data), "mime": mime})
    return d, False


def duplicate_warning(db: Session, d: Document) -> str | None:
    other = db.scalar(select(Document.expense_id).where(
        Document.household_id == d.household_id, Document.sha256 == d.sha256, Document.expense_id != d.expense_id))
    return str(other) if other else None
