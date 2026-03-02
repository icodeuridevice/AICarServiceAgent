"""Vehicle intelligence report aggregation service."""

from datetime import date, timedelta
from typing import TypedDict

from sqlalchemy.orm import Session

from garage_agent.services.intelligence_service import get_vehicle_service_history
from garage_agent.services.issue_detection_service import detect_recurring_issues
from garage_agent.services.prediction_service import predict_next_service_date

SERVICE_STALENESS_DAYS = 180
BASE_HEALTH_SCORE = 100


class VehicleIntelligenceReport(TypedDict):
    """Aggregated vehicle intelligence response payload."""

    vehicle_id: int
    total_services: int
    last_service_date: date | None
    predicted_next_service_date: date | None
    interval_days: int | None
    confidence: float | None
    recurring_issues: list[dict]
    vehicle_health_score: int


def _compute_vehicle_health_score(
    *,
    recurring_issue_count: int,
    last_service_date: date | None,
    confidence: float | None,
) -> int:
    """Compute a deterministic health score bounded to [0, 100]."""
    score = BASE_HEALTH_SCORE

    if recurring_issue_count == 1:
        score -= 10
    elif recurring_issue_count >= 2:
        score -= 20

    stale_cutoff = date.today() - timedelta(days=SERVICE_STALENESS_DAYS)
    if last_service_date is None or last_service_date < stale_cutoff:
        score -= 15

    if confidence is not None and confidence < 0.5:
        score -= 5

    return max(0, min(100, score))


def get_vehicle_intelligence_report(
    db: Session,
    vehicle_id: int,
) -> VehicleIntelligenceReport:
    """Return a single intelligence report for a vehicle.

    This function is read-only and composes:
    - completed service history
    - next-service prediction
    - recurring issue detection

    Args:
        db: SQLAlchemy database session.
        vehicle_id: Target vehicle identifier.

    Returns:
        Aggregated intelligence payload with service counts, timeline, prediction,
        recurring issues, and computed vehicle health score.

    Raises:
        ValueError: If the vehicle does not exist.
    """
    service_history = get_vehicle_service_history(db=db, vehicle_id=vehicle_id)
    total_services = len(service_history)
    last_service_date = service_history[-1]["service_date"] if service_history else None

    recurring_issue_summary = detect_recurring_issues(db=db, vehicle_id=vehicle_id)
    recurring_issues = recurring_issue_summary["recurring_issues"]

    predicted_next_service_date: date | None = None
    interval_days: int | None = None
    confidence: float | None = None

    if total_services > 0:
        prediction = predict_next_service_date(db=db, vehicle_id=vehicle_id)
        predicted_next_service_date = prediction["predicted_next_service_date"]
        interval_days = prediction["interval_days"]
        confidence = prediction["confidence"]

    vehicle_health_score = _compute_vehicle_health_score(
        recurring_issue_count=len(recurring_issues),
        last_service_date=last_service_date,
        confidence=confidence,
    )

    return {
        "vehicle_id": vehicle_id,
        "total_services": total_services,
        "last_service_date": last_service_date,
        "predicted_next_service_date": predicted_next_service_date,
        "interval_days": interval_days,
        "confidence": confidence,
        "recurring_issues": recurring_issues,
        "vehicle_health_score": vehicle_health_score,
    }
