"""Booking-related service helpers."""

from datetime import date, time

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from garage_agent.db.models import Booking, Customer, ServiceBay, Vehicle
from garage_agent.services.vehicle_service import get_or_create_vehicle
from garage_agent.services.audit_service import create_audit_log
from garage_agent.services.slot_service import (
    get_available_slot,
    get_nearby_available_slots,
    reserve_slot,
)
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


def check_slot_conflict(
    db: Session,
    garage_id: int,
    service_date: date,
    service_time: time,
) -> bool:
    active_count = db.scalar(
        select(func.count(Booking.id))
        .select_from(Booking)
        .where(Booking.garage_id == garage_id)
        .where(Booking.service_date == service_date)
        .where(Booking.service_time == service_time)
        .where(Booking.status.in_(ACTIVE_STATUSES))
    )

    return active_count >= MAX_SLOT_CAPACITY


def get_or_create_customer_by_phone(db: Session, garage_id: int, phone: str) -> Customer:
    customer = db.scalar(
        select(Customer)
        .where(Customer.phone == phone)
        .where(Customer.garage_id == garage_id)
    )
    if customer is not None:
        return customer

    customer = Customer(
        phone=phone,
        garage_id=garage_id,
    )
    db.add(customer)
    db.flush()
    return customer


def _get_or_create_vehicle_for_customer(
    db: Session,
    customer_id: int,
    garage_id: int,
    brand: str | None = None,
    model: str | None = None,
) -> Vehicle:
    """Return the customer's vehicle, creating one when missing.

    When *brand* is provided the lookup uses the vehicle service for
    precise brand/model matching.  Without a brand the legacy behaviour
    (return first vehicle, or create an empty one) is preserved.
    """
    customer = db.scalar(
        select(Customer)
        .where(Customer.id == customer_id)
        .where(Customer.garage_id == garage_id)
    )
    if customer is None:
        raise ValueError("Customer not found.")

    # --- Use vehicle service when brand info is available ---
    if brand is not None:
        return get_or_create_vehicle(
            db=db,
            garage_id=garage_id,
            customer_id=customer_id,
            brand=brand,
            model=model,
        )

    # --- Legacy fallback: first vehicle or create empty ---
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


def _apply_completion_intelligence(db: Session, garage_id: int, booking: Booking) -> None:
    if booking.garage_id != garage_id:
        raise DomainException(
            code=ErrorCode.BOOKING_NOT_FOUND,
            message="Booking not found."
        )

    if booking.vehicle is None:
        raise ValueError("Booking vehicle not found.")

    booking.vehicle.last_service_date = booking.service_date
    booking.vehicle.next_service_due_date = calculate_next_service(
        service_type=booking.service_type,
        service_date=booking.service_date,
    )
    update_customer_health(
        db=db,
        garage_id=garage_id,
        customer_id=booking.vehicle.customer_id,
    )


def _get_booking_customer_id(booking: Booking) -> int:
    if booking.vehicle is None:
        raise ValueError("Booking vehicle not found.")
    return booking.vehicle.customer_id


def _format_time_label(t: str) -> str:
    """Convert 'HH:MM' (24h) to human-readable '3:00 PM' style."""
    h, m = int(t[:2]), int(t[3:])
    suffix = "AM" if h < 12 else "PM"
    display_h = h % 12 or 12
    return f"{display_h}:{m:02d} {suffix}"


def create_booking(
    db: Session,
    garage_id: int,
    customer_id: int,
    service_type: str,
    service_date: date,
    service_time: time,
    vehicle: dict | None = None,
) -> Booking:
    """Create a booking when the requested slot has no active conflict."""
    if check_slot_conflict(
        db=db,
        garage_id=garage_id,
        service_date=service_date,
        service_time=service_time,
    ):
        raise DomainException(
            code=ErrorCode.SLOT_CONFLICT,
            message="Selected time slot is already booked."
        )

    # --- Bay-slot availability (only when bays are configured) ---
    time_label = service_time.strftime("%H:%M")
    has_bays = db.scalar(
        select(ServiceBay.id)
        .where(ServiceBay.garage_id == garage_id)
        .where(ServiceBay.is_active.is_(True))
    ) is not None

    assigned_bay_id: int | None = None

    if has_bays:
        slot = get_available_slot(
            db=db,
            garage_id=garage_id,
            service_date=service_date,
            service_time=time_label,
        )
        if slot is None:
            alternatives = get_nearby_available_slots(
                db=db,
                garage_id=garage_id,
                service_date=service_date,
                service_time=time_label,
            )
            if alternatives:
                alt_display = ", ".join(_format_time_label(t) for t in alternatives)
                msg = (
                    f"That time slot is full. "
                    f"Available times are {alt_display}."
                )
            else:
                msg = "Selected time is full and no other slots are available for this date."

            logger.warning(
                "Slot full for garage_id=%s date=%s time=%s",
                garage_id,
                service_date,
                time_label,
                extra={"event": "slot_full", "garage_id": garage_id},
            )
            raise DomainException(code=ErrorCode.SLOT_FULL, message=msg)

        reserve_slot(db=db, slot=slot)
        assigned_bay_id = slot.bay_id

    # --- Extract vehicle brand/model ---
    v_brand: str | None = None
    v_model: str | None = None
    if isinstance(vehicle, dict):
        v_brand = vehicle.get("brand")
        v_model = vehicle.get("model")

    try:
        resolved_vehicle = _get_or_create_vehicle_for_customer(
            db=db,
            customer_id=customer_id,
            garage_id=garage_id,
            brand=v_brand,
            model=v_model,
        )

        logger.info(
            "event=vehicle_linked_to_booking vehicle_id=%s brand=%s model=%s",
            resolved_vehicle.id,
            v_brand,
            v_model,
        )

        booking = Booking(
            vehicle_id=resolved_vehicle.id,
            garage_id=garage_id,
            service_type=service_type,
            service_date=service_date,
            service_time=service_time,
            status="PENDING",
            bay_id=assigned_bay_id,
        )

        db.add(booking)
        db.commit()
        db.refresh(booking)

        create_audit_log(
            db=db,
            garage_id=garage_id,
            action_type="BOOKING_CREATED",
            entity_type="Booking",
            entity_id=booking.id,
            metadata={
                "customer_id": customer_id,
                "service_type": service_type,
                "service_date": str(service_date),
                "service_time": str(service_time),
                "bay_id": assigned_bay_id,
            },
        )

        logger.info(
            "Booking created",
            extra={
                "booking_id": booking.id,
                "customer_id": customer_id,
                "bay_id": assigned_bay_id,
            },
        )

        return booking
    except SQLAlchemyError:
        db.rollback()
        raise


def update_booking_status(db: Session, garage_id: int, booking_id: int, new_status: str) -> Booking:
    """Update booking status when the requested transition is allowed."""
    booking = db.scalar(
        select(Booking)
        .where(Booking.id == booking_id)
        .where(Booking.garage_id == garage_id)
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
            _apply_completion_intelligence(db=db, garage_id=garage_id, booking=booking)
        elif new_status == "CANCELLED":
            update_customer_health(
                db=db,
                garage_id=garage_id,
                customer_id=_get_booking_customer_id(booking),
            )

        db.commit()
        db.refresh(booking)
        return booking
    except SQLAlchemyError:
        db.rollback()
        raise


def reschedule_booking(
    db: Session,
    garage_id: int,
    booking_id: int,
    new_date: date,
    new_time: time,
) -> Booking:
    booking = db.scalar(
        select(Booking)
        .where(Booking.id == booking_id)
        .where(Booking.garage_id == garage_id)
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
    if check_slot_conflict(
        db=db,
        garage_id=garage_id,
        service_date=new_date,
        service_time=new_time,
    ):
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


def cancel_booking(db: Session, garage_id: int, booking_id: int) -> Booking:
    booking = db.scalar(
        select(Booking)
        .where(Booking.id == booking_id)
        .where(Booking.garage_id == garage_id)
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
        update_customer_health(
            db=db,
            garage_id=garage_id,
            customer_id=_get_booking_customer_id(booking),
        )

        db.commit()
        db.refresh(booking)

        create_audit_log(
            db=db,
            garage_id=garage_id,
            action_type="BOOKING_CANCELLED",
            entity_type="Booking",
            entity_id=booking.id,
            metadata={"previous_status": "PENDING/CONFIRMED"},
        )

        return booking

    except SQLAlchemyError:
        db.rollback()
        raise
