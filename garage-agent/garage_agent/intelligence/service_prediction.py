"""Deterministic service interval prediction helpers."""

from datetime import date, timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from garage_agent.db.models import Vehicle

DEFAULT_SERVICE_INTERVAL_DAYS: Final[int] = 120
DUE_WINDOW_DAYS: Final[int] = 3
SERVICE_INTERVAL_DAYS: Final[dict[str, int]] = {
    "oil_change": 90,
    "general_service": 180,
    "full_service": 365,
}


def calculate_next_service(service_type: str, service_date: date) -> date:
    """Return next due date based on deterministic service intervals."""
    normalized_service_type = service_type.strip().lower()
    interval_days = SERVICE_INTERVAL_DAYS.get(
        normalized_service_type,
        DEFAULT_SERVICE_INTERVAL_DAYS,
    )
    return service_date + timedelta(days=interval_days)


def get_due_vehicles(db: Session) -> list[Vehicle]:
    """Return vehicles with service due in the next 3 days (inclusive)."""
    due_threshold = date.today() + timedelta(days=DUE_WINDOW_DAYS)
    return db.scalars(
        select(Vehicle)
        .where(Vehicle.next_service_due_date.is_not(None))
        .where(Vehicle.next_service_due_date <= due_threshold)
    ).all()
