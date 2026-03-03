"""Audit logging service – records critical entity lifecycle events."""

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from garage_agent.db.models import AuditLog

logger = logging.getLogger(__name__)


def create_audit_log(
    db: Session,
    garage_id: int,
    action_type: str,
    entity_type: str,
    entity_id: int,
    user_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist an audit entry for a business event."""
    log = AuditLog(
        garage_id=garage_id,
        user_id=user_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        extra=json.dumps(metadata) if metadata else None,
    )
    db.add(log)
    db.commit()

    logger.info(
        "AUDIT | %s | %s #%s | garage=%s user=%s",
        action_type,
        entity_type,
        entity_id,
        garage_id,
        user_id,
    )
