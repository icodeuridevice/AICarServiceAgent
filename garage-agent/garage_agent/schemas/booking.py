from pydantic import BaseModel
from datetime import date, time

class BookingSummaryResponse(BaseModel):
    total: int
    pending: int = 0
    confirmed: int = 0
    in_progress: int = 0
    completed: int = 0
    cancelled: int = 0


class BookingListItem(BaseModel):
    booking_id: int
    customer_phone: str
    service_type: str
    service_date: date
    service_time: time
    status: str


class TodayBookingItem(BaseModel):
    booking_id: int
    customer_phone: str
    service_type: str
    service_time: time
    status: str


class BookingStatusResponse(BaseModel):
    booking_id: int
    status: str


class RescheduleResponse(BaseModel):
    booking_id: int
    new_date: date
    new_time: time
    status: str


class CancelResponse(BaseModel):
    booking_id: int
    status: str