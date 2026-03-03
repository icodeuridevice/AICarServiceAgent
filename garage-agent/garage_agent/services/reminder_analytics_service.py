"""Analytics helpers for the reminder subsystem."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from garage_agent.db.models import Reminder


def get_reminder_stats(db: Session, garage_id: int) -> dict:
    """Return aggregate reminder statistics for a single garage.

    Keys returned:
        total, auto_booked, expired, ignored
    """
    return {
        "total": db.scalar(
            select(func.count()).where(Reminder.garage_id == garage_id)
        ),
        "auto_booked": db.scalar(
            select(func.count()).where(
                Reminder.garage_id == garage_id,
                Reminder.status == "AUTO_BOOKED",
            )
        ),
        "expired": db.scalar(
            select(func.count()).where(
                Reminder.garage_id == garage_id,
                Reminder.status == "EXPIRED",
            )
        ),
        "ignored": db.scalar(
            select(func.count()).where(
                Reminder.garage_id == garage_id,
                Reminder.status == "IGNORED",
            )
        ),
    }
