from sqlalchemy.orm import Session

from garage_agent.services.vehicle_intelligence_service import (
    get_vehicle_intelligence_report,
)


def tool_analyze_vehicle_health(
    db: Session,
    vehicle_id: int,
):
    return get_vehicle_intelligence_report(
        db=db,
        vehicle_id=vehicle_id,
    )
