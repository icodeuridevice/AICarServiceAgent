"""Booking-related service helpers."""

from datetime import date, time

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.models import Booking, Customer, Vehicle

ACTIVE_STATUSES = ("PENDING", "CONFIRMED", "IN_PROGRESS")
ALLOWED_TRANSITIONS = {
    "PENDING": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


def check_slot_conflict(db: Session, service_date: date, service_time: time) -> bool:
    """Return whether an active booking already occupies the same slot."""
    existing_booking_id = db.scalar(
        select(Booking.id)
        .where(Booking.service_date == service_date)
        .where(Booking.service_time == service_time)
        .where(Booking.status.in_(ACTIVE_STATUSES))
        .limit(1)
    )
    return existing_booking_id is not None


def _get_or_create_vehicle_for_customer(db: Session, customer_id: int) -> Vehicle:
    """Return the customer's first vehicle, creating one when missing."""
    customer = db.scalar(select(Customer).where(Customer.id == customer_id))
    if customer is None:
        raise ValueError("Customer not found.")

    vehicle = db.scalar(
        select(Vehicle).where(Vehicle.customer_id == customer_id).order_by(Vehicle.id.asc())
    )
    if vehicle is None:
        vehicle = Vehicle(customer_id=customer_id)
        db.add(vehicle)
        db.flush()
    return vehicle


def create_booking(
    db: Session,
    customer_id: int,
    service_type: str,
    service_date: date,
    service_time: time,
) -> Booking:
    """Create a booking when the requested slot has no active conflict."""
    if check_slot_conflict(db=db, service_date=service_date, service_time=service_time):
        raise ValueError("Selected time slot is already booked.")

    try:
        vehicle = _get_or_create_vehicle_for_customer(db=db, customer_id=customer_id)
        booking = Booking(
            vehicle_id=vehicle.id,
            service_type=service_type,
            service_date=service_date,
            service_time=service_time,
            status="PENDING",
        )

        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking
    except SQLAlchemyError:
        db.rollback()
        raise


def update_booking_status(db: Session, booking_id: int, new_status: str) -> Booking:
    """Update booking status when the requested transition is allowed."""
    booking = db.scalar(select(Booking).where(Booking.id == booking_id))
    if booking is None:
        raise ValueError("Booking not found.")

    current_status = booking.status
    allowed_next_statuses = ALLOWED_TRANSITIONS.get(current_status, set())
    if new_status not in allowed_next_statuses:
        raise ValueError("Invalid status transition.")

    try:
        booking.status = new_status
        db.commit()
        db.refresh(booking)
        return booking
    except SQLAlchemyError:
        db.rollback()
        raise
