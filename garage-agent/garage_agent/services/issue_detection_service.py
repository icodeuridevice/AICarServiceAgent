"""Recurring issue detection for vehicle service history."""

from collections import Counter
from typing import TypedDict

from sqlalchemy.orm import Session

from garage_agent.services.intelligence_service import get_vehicle_completed_services


class RecurringIssueItem(TypedDict):
    """Detected recurring issue metadata for a single service type."""

    service_type: str
    occurrences: int
    severity: str


class RecurringIssueSummary(TypedDict):
    """Recurring issue summary for a vehicle."""

    recurring_issues: list[RecurringIssueItem]
    total_services: int


def _severity_for_occurrences(occurrences: int) -> str:
    """Map occurrence counts to severity levels."""
    if occurrences >= 3:
        return "high"
    return "medium"


def detect_recurring_issues(db: Session, vehicle_id: int, garage_id: int) -> RecurringIssueSummary:
    """Detect recurring service issues for a vehicle.

    The function is read-only and derives issue frequency from completed
    service records.

    Args:
        db: SQLAlchemy database session.
        vehicle_id: Target vehicle identifier.
        garage_id: Garage scope for isolation.

    Returns:
        A summary containing recurring service types (>=2 occurrences) and
        total completed service count.

    Raises:
        ValueError: If the vehicle does not exist.
    """
    completed_services = get_vehicle_completed_services(db=db, vehicle_id=vehicle_id, garage_id=garage_id)
    total_services = len(completed_services)

    if total_services == 0:
        return {"recurring_issues": [], "total_services": 0}

    service_type_counts = Counter(service["service_type"] for service in completed_services)

    recurring_issues: list[RecurringIssueItem] = []
    for service_type, occurrences in sorted(service_type_counts.items()):
        if occurrences < 2:
            continue
        recurring_issues.append(
            {
                "service_type": service_type,
                "occurrences": occurrences,
                "severity": _severity_for_occurrences(occurrences),
            }
        )

    return {
        "recurring_issues": recurring_issues,
        "total_services": total_services,
    }
