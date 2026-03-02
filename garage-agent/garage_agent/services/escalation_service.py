from sqlalchemy.orm import Session

from garage_agent.db.models import Escalation


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
    return escalation
