"""Deterministic auto-booking triggered by reminder reply keywords."""

import logging
from datetime import time

from sqlalchemy.orm import Session

from garage_agent.db.models import Booking
from garage_agent.services.booking_service import (
    create_booking,
    get_or_create_customer_by_phone,
)
from garage_agent.services.reminder_service import (
    get_active_reminder,
    mark_reminder_accepted,
)

logger = logging.getLogger(__name__)

DEFAULT_SERVICE_TIME = time(10, 0)  # 10:00 AM


def auto_book_from_reminder(
    db: Session,
    garage_id: int,
    phone: str,
) -> Booking | None:
    """Create a booking from an active predictive reminder.

    Returns the new ``Booking`` on success, or ``None`` when no active
    reminder exists for the given garage + phone combination.
    """
    reminder = get_active_reminder(db=db, garage_id=garage_id, phone=phone)
    if reminder is None:
        return None

    customer = get_or_create_customer_by_phone(
        db=db,
        garage_id=garage_id,
        phone=phone,
    )

    booking = create_booking(
        db=db,
        garage_id=garage_id,
        customer_id=customer.id,
        service_type=reminder.service_type,
        service_date=reminder.predicted_date,
        service_time=DEFAULT_SERVICE_TIME,
    )

    mark_reminder_accepted(db=db, reminder=reminder)

    logger.info(
        "Auto-booked from reminder: booking_id=%s, phone=%s, garage_id=%s",
        booking.id,
        phone,
        garage_id,
    )

    return booking
