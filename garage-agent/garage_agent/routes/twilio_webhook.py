from fastapi import APIRouter, Form, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from garage_agent.db.session import get_db
from garage_agent.db.models import Booking
from garage_agent.core.response import success_response

router = APIRouter(prefix="/twilio", tags=["twilio"])


@router.post("/status")
def twilio_status_callback(
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
    db: Session = Depends(get_db),
):
    # NOTE: MessageSid is globally unique (Twilio-assigned), so no cross-garage
    # risk exists here.  The lookup is safe without an explicit garage_id filter.
    booking = (
        db.query(Booking)
        .filter(Booking.reminder_message_sid == MessageSid)
        .first()
    )

    if booking:
        booking.delivery_status = MessageStatus

        if MessageStatus == "delivered":
            booking.delivered_at = datetime.now(timezone.utc)

        db.commit()

    return success_response(message="Status received")