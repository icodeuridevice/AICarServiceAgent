from datetime import date

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager

from db.session import get_db
from db.models import Booking, Customer, Vehicle

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


@router.get("/")
def list_bookings(
    status: str | None = None,
    service_date: date | None = None,
    phone: str | None = None,
    db: Session = Depends(get_db),
):
    query = (
        select(Booking)
        .join(Booking.vehicle)
        .join(Vehicle.customer)
        .options(contains_eager(Booking.vehicle).contains_eager(Vehicle.customer))
    )

    if status is not None:
        query = query.where(Booking.status == status.upper())
    if service_date is not None:
        query = query.where(Booking.service_date == service_date)
    if phone is not None:
        query = query.where(Customer.phone == phone)

    bookings = db.execute(query).scalars().all()

    return [
        {
            "booking_id": booking.id,
            "customer_phone": booking.vehicle.customer.phone,
            "service_type": booking.service_type,
            "service_date": booking.service_date.isoformat(),
            "service_time": booking.service_time.isoformat(),
            "status": booking.status,
        }
        for booking in bookings
    ]


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
