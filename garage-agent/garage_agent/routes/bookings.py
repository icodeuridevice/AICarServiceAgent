from datetime import date, time

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, contains_eager

from garage_agent.db.bootstrap import (
    resolve_default_garage_context,
    resolve_garage_from_phone,
)
from garage_agent.db.session import get_db
from garage_agent.db.models import Booking, Customer, Vehicle
from garage_agent.services.booking_service import update_booking_status

from garage_agent.schemas.common import APIResponse
from garage_agent.schemas.booking import BookingSummaryResponse

from typing import List
from garage_agent.schemas.booking import (
    BookingListItem,
    TodayBookingItem,
    BookingStatusResponse,
    RescheduleResponse,
    CancelResponse,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _resolve_route_garage_id(db: Session, phone: str | None = None) -> int:
    if phone:
        return resolve_garage_from_phone(db=db, phone=phone).garage_id
    return resolve_default_garage_context(db=db).garage_id


class StatusUpdate(BaseModel):
    status: str

class RescheduleRequest(BaseModel):
    booking_id: int
    service_date: date
    service_time: time

ALLOWED_STATUSES = ["PENDING", "CONFIRMED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]

@router.get("/", response_model=APIResponse[List[BookingListItem]])
def list_bookings(
    status: str | None = None,
    service_date: date | None = None,
    phone: str | None = None,
    db: Session = Depends(get_db),
):
    garage_id = _resolve_route_garage_id(db=db, phone=phone)
    query = (
        select(Booking)
        .join(Booking.vehicle)
        .join(Vehicle.customer)
        .options(contains_eager(Booking.vehicle).contains_eager(Vehicle.customer))
        .where(Booking.garage_id == garage_id)
    )

    if status is not None:
        query = query.where(Booking.status == status.upper())
    if service_date is not None:
        query = query.where(Booking.service_date == service_date)
    if phone is not None:
        query = query.where(Customer.phone == phone)

    bookings = db.execute(query).scalars().all()

    return APIResponse(
    success=True,
    data=[
        BookingListItem(
            booking_id=booking.id,
            customer_phone=booking.vehicle.customer.phone,
            service_type=booking.service_type,
            service_date=booking.service_date,
            service_time=booking.service_time,
            status=booking.status,
        )
        for booking in bookings
    ],
)


@router.get("/today", response_model=APIResponse[List[TodayBookingItem]])
def list_todays_bookings(db: Session = Depends(get_db)):
    garage_id = _resolve_route_garage_id(db=db)
    today = date.today()

    rows = db.execute(
        select(
            Booking.id.label("booking_id"),
            Customer.phone.label("customer_phone"),
            Booking.service_type,
            Booking.service_time,
            Booking.status,
        )
        .join(Booking.vehicle)
        .join(Vehicle.customer)
        .where(Booking.garage_id == garage_id)
        .where(Booking.service_date == today)
        .order_by(Booking.service_time.asc())
    ).all()

    return APIResponse(
    success=True,
    data=[
        TodayBookingItem(
            booking_id=row.booking_id,
            customer_phone=row.customer_phone,
            service_type=row.service_type,
            service_time=row.service_time,
            status=row.status,
        )
        for row in rows
    ],
)


@router.get("/summary", response_model=APIResponse[BookingSummaryResponse])
def bookings_summary(db: Session = Depends(get_db)):
    garage_id = _resolve_route_garage_id(db=db)
    counts_by_status = {status.lower(): 0 for status in ALLOWED_STATUSES}

    rows = db.execute(
        select(Booking.status, func.count(Booking.id))
        .where(Booking.garage_id == garage_id)
        .group_by(Booking.status)
    ).all()

    total = 0
    for status, count in rows:
        total += count
        normalized_status = status.lower()
        if normalized_status in counts_by_status:
            counts_by_status[normalized_status] = count

    return APIResponse(
        success=True,
        data=BookingSummaryResponse(
            total=total,
            **counts_by_status
        )
    )

@router.patch("/{booking_id}/status", response_model=APIResponse[BookingStatusResponse])
def update_status(booking_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    garage_id = _resolve_route_garage_id(db=db)
    new_status = payload.status.upper()

    if new_status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    booking = update_booking_status(
        db=db,
        garage_id=garage_id,
        booking_id=booking_id,
        new_status=new_status,
    )

    return APIResponse(
    success=True,
    data=BookingStatusResponse(
        booking_id=booking.id,
        status=booking.status,
    ),
)


@router.put("/reschedule", response_model=APIResponse[RescheduleResponse])
def reschedule_booking(
    payload: RescheduleRequest,
    db: Session = Depends(get_db),
):
    garage_id = _resolve_route_garage_id(db=db)
    from garage_agent.services.booking_service import reschedule_booking as reschedule_engine

    booking = reschedule_engine(
        db=db,
        garage_id=garage_id,
        booking_id=payload.booking_id,
        new_date=payload.service_date,
        new_time=payload.service_time,
    )

    return APIResponse(
    success=True,
    data=RescheduleResponse(
        booking_id=booking.id,
        new_date=booking.service_date,
        new_time=booking.service_time,
        status=booking.status,
    ),
)


@router.patch("/{booking_id}/cancel", response_model=APIResponse[CancelResponse])
def cancel(
    booking_id: int,
    db: Session = Depends(get_db),
):
    garage_id = _resolve_route_garage_id(db=db)
    from garage_agent.services.booking_service import cancel_booking

    booking = cancel_booking(db=db, garage_id=garage_id, booking_id=booking_id)

    return APIResponse(
    success=True,
    data=CancelResponse(
        booking_id=booking.id,
        status=booking.status,
    ),
)
