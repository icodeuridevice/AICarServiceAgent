from fastapi import APIRouter, Form, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from db.session import get_db
from db.models import Booking

router = APIRouter(prefix="/twilio", tags=["twilio"])


@router.post("/status")
def twilio_status_callback(
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
    db: Session = Depends(get_db),
):
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

    return {"received": True}