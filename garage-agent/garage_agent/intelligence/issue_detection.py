"""Deterministic issue detection helpers."""

from datetime import date, timedelta
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from garage_agent.db.models import Booking

REPEATED_ISSUE_LOOKBACK_DAYS: Final[int] = 180
REPEATED_ISSUE_THRESHOLD: Final[int] = 2


def detect_repeated_issue(
    db: Session,
    garage_id: int,
    vehicle_id: int,
    service_type: str,
) -> bool:
    """Return True if the same service occurred >= 2 times in the last 6 months."""
    service_type_normalized = service_type.strip().lower()
    today = date.today()
    cutoff_date = today - timedelta(days=REPEATED_ISSUE_LOOKBACK_DAYS)

    matching_count = db.scalar(
        select(func.count(Booking.id))
        .where(Booking.garage_id == garage_id)
        .where(Booking.vehicle_id == vehicle_id)
        .where(func.lower(Booking.service_type) == service_type_normalized)
        .where(Booking.service_date >= cutoff_date)
        .where(Booking.service_date <= today)
    ) or 0

    return matching_count >= REPEATED_ISSUE_THRESHOLD
