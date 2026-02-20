"""Webhook routes for inbound garage-agent messages.

Keep this module focused on transport concerns (HTTP + parsing).
Business logic can be delegated to `services/` as it grows.
"""

import logging
from datetime import date, datetime, time, timedelta
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.models import Booking, Customer, Vehicle
from db.session import get_db
from services.conversation_service import (
    clear_state,
    get_data,
    get_state,
    set_state,
    update_data,
)
from services.extractor import extract_booking_details

router = APIRouter(tags=["webhook"])
logger = logging.getLogger(__name__)


def _build_twiml_reply(reply_text: str) -> str:
    """Wrap plain text in a TwiML XML message response."""
    safe_reply_text = escape(reply_text)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f"    <Message>{safe_reply_text}</Message>\n"
        "</Response>"
    )


def _parse_service_date(raw_date: str | None) -> date | None:
    """Convert extracted date text into a `date` object."""
    if raw_date is None:
        return None

    normalized = raw_date.strip().lower()
    if not normalized:
        return None

    today = date.today()
    if normalized == "today":
        return today
    if normalized == "tomorrow":
        return today + timedelta(days=1)

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue

    separator = "/" if "/" in normalized else "-" if "-" in normalized else None
    if separator is None:
        return None

    date_parts = normalized.split(separator)
    if len(date_parts) != 2:
        return None

    try:
        day = int(date_parts[0])
        month = int(date_parts[1])
    except ValueError:
        return None

    for candidate_year in (today.year, today.year + 1):
        try:
            candidate_date = date(candidate_year, month, day)
        except ValueError:
            continue
        if candidate_date >= today:
            return candidate_date

    return None


def _parse_service_time(raw_time: str | None) -> time | None:
    """Convert extracted time text into a `time` object."""
    if raw_time is None:
        return None

    normalized = raw_time.strip().lower()
    if not normalized:
        return None

    if normalized == "noon":
        return time(hour=12, minute=0)
    if normalized == "midnight":
        return time(hour=0, minute=0)

    compact_time = normalized.replace(" ", "").replace(".", ":")
    for fmt in ("%H:%M", "%H", "%I:%M%p", "%I%p"):
        try:
            return datetime.strptime(compact_time, fmt).time()
        except ValueError:
            continue

    return None


def _get_or_create_customer(db: Session, phone: str) -> Customer:
    """Fetch customer by phone or create a new one."""
    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if customer is None:
        customer = Customer(phone=phone)
        db.add(customer)
        db.flush()
    return customer


def _get_or_create_vehicle(db: Session, customer_id: int) -> Vehicle:
    """Fetch a customer's first vehicle or create one."""
    vehicle = db.scalar(
        select(Vehicle).where(Vehicle.customer_id == customer_id).order_by(Vehicle.id.asc())
    )
    if vehicle is None:
        vehicle = Vehicle(customer_id=customer_id)
        db.add(vehicle)
        db.flush()
    return vehicle


def _persist_booking(
    db: Session,
    phone: str,
    service_type: str,
    service_date: date,
    service_time: time,
) -> None:
    """Persist final booking details with relational links."""
    try:
        customer = _get_or_create_customer(db=db, phone=phone)
        vehicle = _get_or_create_vehicle(db=db, customer_id=customer.id)

        booking = Booking(
            vehicle_id=vehicle.id,
            service_type=service_type,
            service_date=service_date,
            service_time=service_time,
            status="PENDING",
        )

        db.add(booking)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to store booking for phone=%s", phone)
        raise HTTPException(status_code=500, detail="Failed to store booking.") from None


@router.post("/webhook")
async def receive_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    """Receive webhook payloads from external messaging channels."""
    phone = From.replace("whatsapp:", "")
    message = Body.strip()

    # Log the incoming request for operational visibility.
    logger.info("Incoming webhook message from %s: %s", phone, message)

    # Keep extraction logic active for every inbound message.
    extracted_details = extract_booking_details(message)
    detected_service_type = extracted_details.get("service_type") or "general_service"
    detected_service_date = extracted_details.get("service_date")
    detected_service_time = extracted_details.get("service_time")

    state = get_state(phone)
    logger.info("Current conversation state for %s: %s", phone, state or "None")

    if state is None:
        update_data(phone, "initial_message", message)
        update_data(phone, "service_type", detected_service_type)

        if detected_service_date is None:
            set_state(phone, "waiting_for_date")
            reply = "Thanks. Please share your preferred service date."
        else:
            update_data(phone, "service_date", detected_service_date)
            if detected_service_time:
                update_data(phone, "service_time", detected_service_time)
            set_state(phone, "waiting_for_time")
            reply = (
                f"Great. What time works for your {detected_service_type} on "
                f"{detected_service_date}?"
            )
    elif state == "waiting_for_date":
        chosen_date = detected_service_date or message
        update_data(phone, "service_date", chosen_date)
        if "service_type" not in get_data(phone):
            update_data(phone, "service_type", detected_service_type)
        set_state(phone, "waiting_for_time")
        reply = "Got it. What time would you prefer?"
    elif state == "waiting_for_time":
        resolved_service_time = detected_service_time or message
        update_data(phone, "service_time", resolved_service_time)
        conversation_data = get_data(phone)

        service_type = str(conversation_data.get("service_type") or detected_service_type)
        service_date_raw = conversation_data.get("service_date")
        service_time_raw = conversation_data.get("service_time")

        parsed_service_date = _parse_service_date(
            str(service_date_raw) if service_date_raw is not None else None
        )
        if parsed_service_date is None:
            set_state(phone, "waiting_for_date")
            reply = "I could not understand the date. Please share a date like 24/02 or today."
            twiml_response = _build_twiml_reply(reply)
            return Response(content=twiml_response, media_type="application/xml")

        parsed_service_time = _parse_service_time(
            str(service_time_raw) if service_time_raw is not None else None
        )
        if parsed_service_time is None:
            set_state(phone, "waiting_for_time")
            reply = "I could not understand the time. Please share a time like 10:30 AM."
            twiml_response = _build_twiml_reply(reply)
            return Response(content=twiml_response, media_type="application/xml")

        clear_state(phone)
        _persist_booking(
            db=db,
            phone=phone,
            service_type=service_type,
            service_date=parsed_service_date,
            service_time=parsed_service_time,
        )

        confirmed_date = parsed_service_date.strftime("%Y-%m-%d")
        confirmed_time = parsed_service_time.strftime("%H:%M")
        reply = f"Booking confirmed for {service_type} on {confirmed_date} at {confirmed_time}."
    else:
        clear_state(phone)
        reply = "Let's start again. Please share your service request."

    twiml_response = _build_twiml_reply(reply)
    return Response(content=twiml_response, media_type="application/xml")
