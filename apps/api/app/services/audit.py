import logging

from sqlalchemy.orm import Session

from ..models import AuditLog

log = logging.getLogger("hem.audit")


def audit(db: Session, *, household_id, actor_id, action: str, entity_type: str, entity_id=None, details: dict | None = None):
    """Append an audit row. Details must not contain PII (no names/emails/receipt text)."""
    db.add(AuditLog(
        household_id=household_id, actor_id=actor_id, action=action, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None, details=details or {},
    ))
    log.info("audit action=%s entity=%s id=%s", action, entity_type, entity_id)
