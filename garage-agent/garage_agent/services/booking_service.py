"""Booking-related service helpers."""

from datetime import date, time

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from garage_agent.db.bootstrap import get_default_garage
from garage_agent.db.models import Booking, Customer, Vehicle
from garage_agent.intelligence.customer_health import update_customer_health
from garage_agent.intelligence.service_prediction import calculate_next_service

from garage_agent.core.domain_exceptions import DomainException
from garage_agent.core.error_codes import ErrorCode

import logging

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("PENDING", "CONFIRMED", "IN_PROGRESS")
MAX_SLOT_CAPACITY = 2  # configurable
ALLOWED_TRANSITIONS = {
    "PENDING": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


def check_slot_conflict(db: Session, service_date: date, service_time: time) -> bool:
    garage = get_default_garage(db)
    active_count = db.scalar(
        select(func.count(Booking.id))
        .select_from(Booking)
        .where(Booking.garage_id == garage.id)
        .where(Booking.service_date == service_date)
        .where(Booking.service_time == service_time)
        .where(Booking.status.in_(ACTIVE_STATUSES))
    )

    return active_count >= MAX_SLOT_CAPACITY


def get_or_create_customer_by_phone(db: Session, phone: str) -> Customer:
    garage = get_default_garage(db)

    customer = db.scalar(
        select(Customer)
        .where(Customer.phone == phone)
        .where(Customer.garage_id == garage.id)
    )
    if customer is not None:
        return customer

    customer = Customer(
        phone=phone,
        garage_id=garage.id,
    )
    db.add(customer)
    db.flush()
    return customer


def _get_or_create_vehicle_for_customer(db: Session, customer_id: int, garage_id: int) -> Vehicle:
    """Return the customer's first vehicle, creating one when missing."""
    customer = db.scalar(
        select(Customer)
        .where(Customer.id == customer_id)
        .where(Customer.garage_id == garage_id)
    )
    if customer is None:
        raise ValueError("Customer not found.")

    vehicle = db.scalar(
        select(Vehicle)
        .where(Vehicle.customer_id == customer_id)
        .where(Vehicle.garage_id == garage_id)
        .order_by(Vehicle.id.asc())
    )
    if vehicle is None:
        vehicle = Vehicle(
            customer_id=customer_id,
            garage_id=garage_id,
        )
        db.add(vehicle)
        db.flush()
    return vehicle


def _apply_completion_intelligence(db: Session, booking: Booking) -> None:
    if booking.vehicle is None:
        raise ValueError("Booking vehicle not found.")

    booking.vehicle.next_service_due_date = calculate_next_service(
        service_type=booking.service_type,
        service_date=booking.service_date,
    )
    update_customer_health(db=db, customer_id=booking.vehicle.customer_id)


def _get_booking_customer_id(booking: Booking) -> int:
    if booking.vehicle is None:
        raise ValueError("Booking vehicle not found.")
    return booking.vehicle.customer_id


def create_booking(
    db: Session,
    customer_id: int,
    service_type: str,
    service_date: date,
    service_time: time,
) -> Booking:
    """Create a booking when the requested slot has no active conflict."""
    garage = get_default_garage(db)

    if check_slot_conflict(db=db, service_date=service_date, service_time=service_time):
        raise DomainException(
            code=ErrorCode.SLOT_CONFLICT,
            message="Selected time slot is already booked."
        )

    try:
        vehicle = _get_or_create_vehicle_for_customer(
            db=db,
            customer_id=customer_id,
            garage_id=garage.id,
        )
        booking = Booking(
            vehicle_id=vehicle.id,
            garage_id=garage.id,
            service_type=service_type,
            service_date=service_date,
            service_time=service_time,
            status="PENDING",
        )

        db.add(booking)
        db.commit()
        db.refresh(booking)
        
        logger.info(
            "Booking created",
            extra={
                "booking_id": booking.id,
                "customer_id": customer_id,
            },
        )
        
        return booking
    except SQLAlchemyError:
        db.rollback()
        raise


def update_booking_status(db: Session, booking_id: int, new_status: str) -> Booking:
    """Update booking status when the requested transition is allowed."""
    garage = get_default_garage(db)
    booking = db.scalar(
        select(Booking)
        .where(Booking.id == booking_id)
        .where(Booking.garage_id == garage.id)
    )
    if booking is None:
        raise DomainException(
            code=ErrorCode.BOOKING_NOT_FOUND,
            message="Booking not found."
        )

    current_status = booking.status
    allowed_next_statuses = ALLOWED_TRANSITIONS.get(current_status, set())
    if new_status not in allowed_next_statuses:
        raise DomainException(
            code=ErrorCode.INVALID_STATUS,
            message="Invalid status transition."
        )

    try:
        booking.status = new_status
        if new_status == "COMPLETED":
            _apply_completion_intelligence(db=db, booking=booking)
        elif new_status == "CANCELLED":
            update_customer_health(db=db, customer_id=_get_booking_customer_id(booking))

        db.commit()
        db.refresh(booking)
        return booking
    except SQLAlchemyError:
        db.rollback()
        raise


def reschedule_booking(
    db: Session,
    booking_id: int,
    new_date: date,
    new_time: time,
) -> Booking:
    garage = get_default_garage(db)
    booking = db.scalar(
        select(Booking)
        .where(Booking.id == booking_id)
        .where(Booking.garage_id == garage.id)
    )

    if booking is None:
        raise DomainException(
            code=ErrorCode.BOOKING_NOT_FOUND,
            message="Booking not found."
        )

    if booking.status not in {"PENDING", "CONFIRMED"}:
        raise DomainException(
            code=ErrorCode.INVALID_STATUS,
            message="Only PENDING or CONFIRMED bookings can be rescheduled."
        )

    # Check slot conflict
    if check_slot_conflict(db=db, service_date=new_date, service_time=new_time):
        raise DomainException(
            code=ErrorCode.SLOT_CONFLICT,
            message="Selected time slot is already booked."
        )

    try:
        booking.service_date = new_date
        booking.service_time = new_time

        # Reset lifecycle
        booking.status = "PENDING"
        booking.reminder_sent = False
        booking.reminder_sent_at = None
        booking.reminder_message_sid = None
        booking.delivery_status = None
        booking.delivered_at = None

        db.commit()
        db.refresh(booking)
        return booking

    except SQLAlchemyError:
        db.rollback()
        raise


def cancel_booking(db: Session, booking_id: int) -> Booking:
    garage = get_default_garage(db)
    booking = db.scalar(
        select(Booking)
        .where(Booking.id == booking_id)
        .where(Booking.garage_id == garage.id)
    )

    if booking is None:
        raise DomainException(
            code=ErrorCode.BOOKING_NOT_FOUND,
            message="Booking not found."
        )

    if booking.status not in {"PENDING", "CONFIRMED"}:
        raise DomainException(
            code=ErrorCode.INVALID_STATUS,
            message="Only PENDING or CONFIRMED bookings can be cancelled."
        )

    try:
        booking.status = "CANCELLED"

        # Optional: clear reminder fields
        booking.reminder_sent = False
        booking.reminder_sent_at = None
        booking.reminder_message_sid = None
        booking.delivery_status = None
        booking.delivered_at = None
        update_customer_health(db=db, customer_id=_get_booking_customer_id(booking))

        db.commit()
        db.refresh(booking)
        return booking

    except SQLAlchemyError:
        db.rollback()
        raise
