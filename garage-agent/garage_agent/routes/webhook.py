"""Webhook routes for inbound garage-agent messages.

Transport layer only.
Conversation + booking logic delegated to services.

Async architecture:
  1. Webhook returns an immediate TwiML acknowledgement (<1 s)
  2. AI processing runs in a FastAPI BackgroundTask
  3. Final reply is delivered via the Twilio REST API
"""

import logging
from datetime import date, datetime, time, timedelta
from xml.sax.saxutils import escape

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from garage_agent.db.bootstrap import resolve_garage_from_phone
from garage_agent.db.session import get_db, SessionLocal
from garage_agent.services.conversation_service import (
    clear_state,
    get_data,
    get_state,
    set_state,
    update_data,
)
from garage_agent.services.booking_service import create_booking, get_or_create_customer_by_phone
from garage_agent.services.extractor import extract_booking_details
from garage_agent.services.twilio_client import send_whatsapp_message
from garage_agent.ai.adapter import get_ai_engine

from garage_agent.core.limiter import limiter

router = APIRouter(tags=["webhook"])
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Immediate TwiML acknowledge message
# -------------------------------------------------------------------

_IMMEDIATE_ACK = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<Response>\n"
    "    <Message>Processing your request...</Message>\n"
    "</Response>"
)

_EMPTY_TWIML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<Response />"
)


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


def _send_reply(phone: str, text: str) -> None:
    """Send a WhatsApp reply via Twilio REST API (best-effort)."""
    try:
        send_whatsapp_message(to=phone, body=text)
    except Exception:
        logger.exception(
            "event=twilio_send phase=error phone=%s reply_length=%d",
            phone,
            len(text),
        )


# -------------------------------------------------------------------
# Background AI processing (runs after immediate TwiML response)
# -------------------------------------------------------------------


def _process_ai_in_background(phone: str, incoming_message: str, garage_id: int) -> None:
    """
    Run the full AI agent pipeline and deliver the reply via Twilio
    REST API.  This function is executed as a FastAPI BackgroundTask,
    meaning it runs *after* the webhook has already returned
    an immediate TwiML response to Twilio.

    A fresh DB session is created and closed within this function
    since BackgroundTasks run outside the request lifecycle.
    """
    logger.info(
        "event=background_ai phase=start phone=%s garage_id=%s",
        phone,
        garage_id,
    )

    db: Session = SessionLocal()
    try:
        ai_engine = get_ai_engine()
        selected_engine = "llm" if ai_engine.__class__.__name__ == "LLMEngine" else "rule"

        try:
            raw_ai_response = ai_engine.process(
                db=db,
                garage_id=garage_id,
                phone=phone,
                message=incoming_message,
            )
        except Exception as exc:
            logger.exception("event=background_ai phase=ai_error phone=%s", phone)
            raw_ai_response = {
                "engine": selected_engine,
                "type": "conversation",
                "reply": f"Request processed. (AI error: {exc})",
                "tool": None,
                "arguments": None,
                "result": {"error": str(exc)},
            }

        ai_response = raw_ai_response if isinstance(raw_ai_response, dict) else {}

        if not isinstance(raw_ai_response, dict):
            logger.warning("AI engine returned non-dict response: %r", raw_ai_response)
            ai_response = {
                "engine": selected_engine,
                "type": "conversation",
                "reply": "Request processed.",
                "tool": None,
                "arguments": None,
                "result": {"error": "invalid_ai_response"},
            }

        logger.info("event=background_ai phase=ai_complete AI Output: %s", ai_response)

        reply = ai_response.get("reply") or "Request processed."
        _send_reply(phone, reply)

        logger.info(
            "event=background_ai phase=done phone=%s engine=%s",
            phone,
            ai_response.get("engine"),
        )
    finally:
        db.close()


# -------------------------------------------------------------------
# Main Webhook
# -------------------------------------------------------------------


@router.post("/webhook")
@limiter.limit("30/minute")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Response:
    """
    Receive WhatsApp webhook from Twilio.

    Returns an immediate TwiML response (< 1 s) and schedules
    AI processing as a background task.  The final AI reply is
    delivered asynchronously via the Twilio REST API.
    """

    form = await request.form()

    phone = form.get("From", "").replace("whatsapp:", "")
    incoming_message = form.get("Body", "").strip()
    garage_context = resolve_garage_from_phone(db=db, phone=phone)
    garage_id = garage_context.garage_id
    request.state.garage_id = garage_id

    logger.info(
        "Incoming webhook message from %s (garage_id=%s): %s",
        phone,
        garage_id,
        incoming_message,
    )

    # ------------------------------------------------------------
    # Auto-booking from predictive reminder reply (deterministic)
    # Fast path — runs synchronously within the 15 s window.
    # ------------------------------------------------------------

    lower_msg = incoming_message.strip().lower()
    if lower_msg in ("yes", "book", "ok", "schedule"):
        try:
            from garage_agent.services.auto_booking_service import auto_book_from_reminder

            booking = auto_book_from_reminder(
                db=db,
                garage_id=garage_id,
                phone=phone,
            )

            if booking:
                reply = (
                    f"Booking confirmed for {booking.service_date.strftime('%Y-%m-%d')} "
                    f"at {booking.service_time.strftime('%H:%M')}."
                )
                return Response(
                    content=_build_twiml_reply(reply),
                    media_type="application/xml",
                )
        except Exception:
            logger.exception(
                "Auto-booking from reminder failed for phone=%s, garage_id=%s. "
                "Falling back to normal flow.",
                phone,
                garage_id,
            )

    # ------------------------------------------------------------
    # Rule-based conversation flow (fast, deterministic)
    # Runs synchronously — completes well within 15 s.
    # ------------------------------------------------------------

    state = get_state(phone)
    logger.info("Current conversation state for %s: %s", phone, state or "None")

    if state is not None:
        # User is mid-conversation — handle synchronously
        return _handle_rule_conversation(
            db=db,
            phone=phone,
            garage_id=garage_id,
            incoming_message=incoming_message,
            state=state,
        )

    # ------------------------------------------------------------
    # AI Engine (async — offload to background task)
    # ------------------------------------------------------------

    background_tasks.add_task(
        _process_ai_in_background,
        phone=phone,
        incoming_message=incoming_message,
        garage_id=garage_id,
    )

    logger.info(
        "event=webhook_async phase=queued phone=%s garage_id=%s",
        phone,
        garage_id,
    )

    # Return an immediate acknowledgement so Twilio doesn't time out.
    return Response(content=_IMMEDIATE_ACK, media_type="application/xml")


# -------------------------------------------------------------------
# Synchronous rule-based conversation handler
# -------------------------------------------------------------------


def _handle_rule_conversation(
    db: Session,
    phone: str,
    garage_id: int,
    incoming_message: str,
    state: str,
) -> Response:
    """
    Handle multi-turn rule-based booking conversation.
    Runs synchronously — all paths complete in milliseconds.
    """
    extracted = extract_booking_details(incoming_message)
    detected_service_type = extracted.get("service_type") or "general_service"
    detected_service_date = extracted.get("service_date")
    detected_service_time = extracted.get("service_time")

    if state == "waiting_for_date":
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
            customer = get_or_create_customer_by_phone(
                db=db,
                garage_id=garage_id,
                phone=phone,
            )

            create_booking(
                db=db,
                garage_id=garage_id,
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
