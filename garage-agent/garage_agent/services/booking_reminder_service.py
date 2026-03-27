"""Service layer for scheduling and cancelling booking reminders."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from garage_agent.db.models import BookingReminder

logger = logging.getLogger(__name__)


def schedule_booking_reminders(db: Session, booking) -> None:
    """Create 24h and 2h reminder entries for a booking.

    Skips any reminder whose scheduled_time is already in the past.
    """
    service_dt = datetime.combine(
        booking.service_date,
        booking.service_time,
        tzinfo=timezone.utc,
    )

    reminder_specs = [
        {"type": "24h", "time": service_dt - timedelta(hours=24)},
        {"type": "2h", "time": service_dt - timedelta(hours=2)},
    ]

    now = datetime.now(timezone.utc)
    created = 0

    for spec in reminder_specs:
        if spec["time"] <= now:
            logger.info(
                "event=reminder_skipped reason=past_time booking_id=%s type=%s",
                booking.id,
                spec["type"],
            )
            continue

        reminder = BookingReminder(
            garage_id=booking.garage_id,
            booking_id=booking.id,
            reminder_type=spec["type"],
            scheduled_time=spec["time"],
        )
        db.add(reminder)
        created += 1

        logger.info(
            "event=reminder_scheduled booking_id=%s type=%s scheduled_time=%s",
            booking.id,
            spec["type"],
            spec["time"],
        )

    if created:
        db.commit()


def cancel_booking_reminders(db: Session, booking_id: int) -> int:
    """Mark all unsent reminders for a booking as sent (effectively cancel them).

    Returns the number of reminders cancelled.
    """
    unsent = db.scalars(
        select(BookingReminder)
        .where(BookingReminder.booking_id == booking_id)
        .where(BookingReminder.is_sent.is_(False))
    ).all()

    for reminder in unsent:
        reminder.is_sent = True
        logger.info(
            "event=reminder_cancelled booking_id=%s type=%s",
            booking_id,
            reminder.reminder_type,
        )

    if unsent:
        db.commit()

    return len(unsent)
