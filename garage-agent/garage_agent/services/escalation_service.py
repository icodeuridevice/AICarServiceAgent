import logging

from sqlalchemy.orm import Session

from garage_agent.db.models import Escalation
from garage_agent.services.escalation_alert_service import notify_staff_escalation
from garage_agent.services.audit_service import create_audit_log

logger = logging.getLogger(__name__)


def create_escalation(
    db: Session,
    garage_id: int,
    vehicle_id: int,
    reason: str,
    health_score: int,
) -> Escalation:
    escalation = Escalation(
        garage_id=garage_id,
        vehicle_id=vehicle_id,
        reason=reason,
        health_score=health_score,
    )

    db.add(escalation)
    db.commit()
    db.refresh(escalation)

    create_audit_log(
        db=db,
        garage_id=garage_id,
        action_type="ESCALATION_CREATED",
        entity_type="Escalation",
        entity_id=escalation.id,
        metadata={
            "vehicle_id": vehicle_id,
            "reason": reason,
            "health_score": health_score,
        },
    )

    try:
        notify_staff_escalation(
            vehicle_id=vehicle_id,
            health_score=health_score,
            reason=reason,
        )
    except Exception:
        logger.exception(
            "Unexpected failure while triggering staff escalation alert | escalation_id=%s",
            escalation.id,
        )

    return escalation

