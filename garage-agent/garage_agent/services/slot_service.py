"""Service-bay slot management.

Generates daily time-slots, checks availability, and reserves slots
for the Smart Scheduling Engine.
"""

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from garage_agent.db.models import ServiceBay, TimeSlot

logger = logging.getLogger(__name__)

# Slot generation parameters
SLOT_START_HOUR = 9   # 09:00
SLOT_END_HOUR = 18    # 18:00 (last slot starts at 17:30)
SLOT_INTERVAL_MINUTES = 30


def _generate_time_labels() -> list[str]:
    """Return list of HH:MM strings from 09:00 to 17:30 in 30-min steps."""
    times: list[str] = []
    hour, minute = SLOT_START_HOUR, 0
    while hour < SLOT_END_HOUR:
        times.append(f"{hour:02d}:{minute:02d}")
        minute += SLOT_INTERVAL_MINUTES
        if minute >= 60:
            hour += 1
            minute = 0
    return times


def generate_daily_slots(
    db: Session,
    garage_id: int,
    target_date: date,
) -> int:
    """Generate 30-min slots (09:00–17:30) for each active bay on *target_date*.

    Skips any slot that already exists (idempotent).
    Returns the number of newly created slots.
    """
    bays = db.scalars(
        select(ServiceBay)
        .where(ServiceBay.garage_id == garage_id)
        .where(ServiceBay.is_active.is_(True))
    ).all()

    if not bays:
        logger.info(
            "No active bays for garage_id=%s — skipping slot generation",
            garage_id,
            extra={"event": "slot_generation", "garage_id": garage_id},
        )
        return 0

    time_labels = _generate_time_labels()
    created = 0

    for bay in bays:
        for t in time_labels:
            exists = db.scalar(
                select(TimeSlot.id)
                .where(TimeSlot.garage_id == garage_id)
                .where(TimeSlot.bay_id == bay.id)
                .where(TimeSlot.service_date == target_date)
                .where(TimeSlot.service_time == t)
            )
            if exists is not None:
                continue

            db.add(TimeSlot(
                garage_id=garage_id,
                bay_id=bay.id,
                service_date=target_date,
                service_time=t,
                is_booked=False,
            ))
            created += 1

    db.commit()
    logger.info(
        "Slot generation complete: %d new slots for garage_id=%s on %s",
        created,
        garage_id,
        target_date,
        extra={"event": "slot_generation", "garage_id": garage_id, "date": str(target_date)},
    )
    return created


def get_available_slot(
    db: Session,
    garage_id: int,
    service_date: date,
    service_time: str,
) -> TimeSlot | None:
    """Return the first available (unbooked) slot for the given date + time."""
    slot = db.scalar(
        select(TimeSlot)
        .where(TimeSlot.garage_id == garage_id)
        .where(TimeSlot.service_date == service_date)
        .where(TimeSlot.service_time == service_time)
        .where(TimeSlot.is_booked.is_(False))
    )
    logger.info(
        "Slot check for garage_id=%s date=%s time=%s → %s",
        garage_id,
        service_date,
        service_time,
        "available" if slot else "none",
        extra={"event": "slot_check", "garage_id": garage_id},
    )
    return slot


def get_nearby_available_slots(
    db: Session,
    garage_id: int,
    service_date: date,
    service_time: str,
    limit: int = 3,
) -> list[str]:
    """Return up to *limit* alternative available times on the same date.

    Excludes the originally requested time.
    """
    rows = db.scalars(
        select(TimeSlot.service_time)
        .where(TimeSlot.garage_id == garage_id)
        .where(TimeSlot.service_date == service_date)
        .where(TimeSlot.is_booked.is_(False))
        .where(TimeSlot.service_time != service_time)
        .group_by(TimeSlot.service_time)
        .order_by(TimeSlot.service_time)
        .limit(limit)
    ).all()
    return list(rows)


def reserve_slot(db: Session, slot: TimeSlot) -> None:
    """Mark a slot as booked."""
    slot.is_booked = True
    db.commit()
    logger.info(
        "Slot reserved: slot_id=%s bay_id=%s",
        slot.id,
        slot.bay_id,
        extra={"event": "slot_reserved", "slot_id": slot.id, "bay_id": slot.bay_id},
    )
