"""
Booking tools exposed to AI layer.

These are safe execution wrappers around booking services.
AI never touches database models directly.
"""

from datetime import date, time
from sqlalchemy.orm import Session

from garage_agent.services.booking_service import (
    create_booking,
    reschedule_booking,
    cancel_booking,
    update_booking_status,
)
from garage_agent.services.booking_service import check_slot_conflict


def tool_create_booking(
    db: Session,
    garage_id: int,
    customer_id: int,
    service_type: str,
    service_date: date,
    service_time: time,
):
    return create_booking(
        db=db,
        garage_id=garage_id,
        customer_id=customer_id,
        service_type=service_type,
        service_date=service_date,
        service_time=service_time,
    )


def tool_reschedule_booking(
    db: Session,
    garage_id: int,
    booking_id: int,
    new_date: date,
    new_time: time,
):
    return reschedule_booking(
        db=db,
        garage_id=garage_id,
        booking_id=booking_id,
        new_date=new_date,
        new_time=new_time,
    )


def tool_cancel_booking(
    db: Session,
    garage_id: int,
    booking_id: int,
):
    return cancel_booking(db=db, garage_id=garage_id, booking_id=booking_id)


def tool_update_booking_status(
    db: Session,
    garage_id: int,
    booking_id: int,
    new_status: str,
):
    return update_booking_status(
        db=db,
        garage_id=garage_id,
        booking_id=booking_id,
        new_status=new_status,
    )


def tool_check_slot_conflict(
    db: Session,
    garage_id: int,
    service_date: date,
    service_time: time,
):
    return check_slot_conflict(
        db=db,
        garage_id=garage_id,
        service_date=service_date,
        service_time=service_time,
    )
