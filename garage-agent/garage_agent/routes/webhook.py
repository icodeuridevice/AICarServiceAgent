"""Webhook routes for inbound garage-agent messages.

Transport layer only.
Conversation + booking logic delegated to services.
"""

import logging
from datetime import date, datetime, time, timedelta
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from garage_agent.db.models import Customer
from garage_agent.db.session import get_db
from garage_agent.services.conversation_service import (
    clear_state,
    get_data,
    get_state,
    set_state,
    update_data,
)
from garage_agent.services.booking_service import create_booking
from garage_agent.services.extractor import extract_booking_details
from garage_agent.ai.adapter import get_ai_engine

router = APIRouter(tags=["webhook"])
logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Utility helpers
# -------------------------------------------------------------------


def _build_twiml_reply(reply_text: str) -> str:
    safe_reply_text = escape(reply_text)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f"    <Message>{safe_reply_text}</Message>\n"
        "</Response>"
    )


def _parse_service_date(raw_date: str | None) -> date | None:
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

    return None


def _parse_service_time(raw_time: str | None) -> time | None:
    if raw_time is None:
        return None

    normalized = raw_time.strip().lower()
    if not normalized:
        return None

    if normalized == "noon":
        return time(12, 0)
    if normalized == "midnight":
        return time(0, 0)

    compact_time = normalized.replace(" ", "").replace(".", ":")

    for fmt in ("%H:%M", "%H", "%I:%M%p", "%I%p"):
        try:
            return datetime.strptime(compact_time, fmt).time()
        except ValueError:
            continue

    return None


def _get_or_create_customer(db: Session, phone: str) -> Customer:
    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if customer is None:
        customer = Customer(phone=phone)
        db.add(customer)
        db.flush()
    return customer


# -------------------------------------------------------------------
# Main Webhook
# -------------------------------------------------------------------


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """
    Receive WhatsApp webhook from Twilio.
    """

    form = await request.form()

    phone = form.get("From", "").replace("whatsapp:", "")
    incoming_message = form.get("Body", "").strip()

    logger.info("Incoming webhook message from %s: %s", phone, incoming_message)

    # ------------------------------------------------------------
    # AI Engine (future-proof layer)
    # ------------------------------------------------------------
    ai_engine = get_ai_engine()
    ai_output = ai_engine.process(phone=phone, message=incoming_message)

    logger.info("AI Output: %s", ai_output)

    # ------------------------------------------------------------
    # Rule-based extraction (current stable system)
    # ------------------------------------------------------------
    extracted = extract_booking_details(incoming_message)
    detected_service_type = extracted.get("service_type") or "general_service"
    detected_service_date = extracted.get("service_date")
    detected_service_time = extracted.get("service_time")

    state = get_state(phone)
    logger.info("Current conversation state for %s: %s", phone, state or "None")

    # ------------------------------------------------------------
    # Conversation Flow
    # ------------------------------------------------------------

    if state is None:
        update_data(phone, "initial_message", incoming_message)
        update_data(phone, "service_type", detected_service_type)

        if detected_service_date is None:
            set_state(phone, "waiting_for_date")
            reply = "Thanks. Please share your preferred service date."
        else:
            update_data(phone, "service_date", detected_service_date)
            set_state(phone, "waiting_for_time")
            reply = (
                f"Great. What time works for your {detected_service_type} "
                f"on {detected_service_date}?"
            )

    elif state == "waiting_for_date":
        update_data(phone, "service_date", incoming_message)
        set_state(phone, "waiting_for_time")
        reply = "Got it. What time would you prefer?"

    elif state == "waiting_for_time":
        update_data(phone, "service_time", incoming_message)

        data = get_data(phone)

        parsed_date = _parse_service_date(str(data.get("service_date")))
        parsed_time = _parse_service_time(str(data.get("service_time")))

        if parsed_date is None:
            set_state(phone, "waiting_for_date")
            reply = "I could not understand the date. Please send like 24/02 or today."
            return Response(
                content=_build_twiml_reply(reply),
                media_type="application/xml",
            )

        if parsed_time is None:
            set_state(phone, "waiting_for_time")
            reply = "I could not understand the time. Please send like 10:30 AM."
            return Response(
                content=_build_twiml_reply(reply),
                media_type="application/xml",
            )

        clear_state(phone)

        try:
            customer = _get_or_create_customer(db=db, phone=phone)

            create_booking(
                db=db,
                customer_id=customer.id,
                service_type=data.get("service_type") or "general_service",
                service_date=parsed_date,
                service_time=parsed_time,
            )

        except ValueError as e:
            reply = str(e)
            return Response(
                content=_build_twiml_reply(reply),
                media_type="application/xml",
            )

        reply = (
            f"Booking confirmed for {data.get('service_type')} "
            f"on {parsed_date.strftime('%Y-%m-%d')} "
            f"at {parsed_time.strftime('%H:%M')}."
        )

    else:
        clear_state(phone)
        reply = "Let's start again. Please share your service request."

    return Response(
        content=_build_twiml_reply(reply),
        media_type="application/xml",
    )