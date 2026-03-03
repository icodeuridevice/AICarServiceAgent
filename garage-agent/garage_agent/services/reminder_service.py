"""Service layer for querying and updating predictive reminders."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from garage_agent.db.models import Reminder


def get_active_reminder(db: Session, garage_id: int, phone: str) -> Reminder | None:
    """Return the most recent SENT reminder for the given garage + phone."""
    return db.scalar(
        select(Reminder)
        .where(Reminder.garage_id == garage_id)
        .where(Reminder.phone == phone)
        .where(Reminder.status == "SENT")
        .order_by(Reminder.created_at.desc())
    )


def mark_reminder_accepted(db: Session, reminder: Reminder) -> None:
    """Transition a reminder to ACCEPTED status."""
    reminder.status = "ACCEPTED"
    reminder.responded_at = datetime.utcnow()
    db.commit()

