"""Helpers for proactive service reminder eligibility and state updates."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from garage_agent.db.models import Vehicle

REMINDER_WINDOW_DAYS = 3


def get_due_vehicles(db):
    today = datetime.now(timezone.utc).date()
    reminder_cutoff = today + timedelta(days=REMINDER_WINDOW_DAYS)

    return db.scalars(
        select(Vehicle)
        .where(Vehicle.next_service_date.is_not(None))
        .where(Vehicle.next_service_date <= reminder_cutoff)
    ).all()


def mark_reminder_sent(vehicle):
    vehicle.last_reminder_sent_at = datetime.now(timezone.utc)
