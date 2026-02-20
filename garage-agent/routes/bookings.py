from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.session import get_db
from db.models import Booking

router = APIRouter(prefix="/bookings", tags=["bookings"])


class StatusUpdate(BaseModel):
    status: str


ALLOWED_STATUSES = ["PENDING", "CONFIRMED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]

VALID_TRANSITIONS = {
    "PENDING": ["CONFIRMED", "CANCELLED"],
    "CONFIRMED": ["IN_PROGRESS", "CANCELLED"],
    "IN_PROGRESS": ["COMPLETED"],
    "COMPLETED": [],
    "CANCELLED": [],
}


@router.patch("/{booking_id}/status")
def update_status(booking_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    new_status = payload.status.upper()

    if new_status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    current_status = booking.status

    if new_status not in VALID_TRANSITIONS.get(current_status, []):
        raise HTTPException(status_code=400, detail="Invalid status transition")

    booking.status = new_status
    db.commit()
    db.refresh(booking)

    return booking