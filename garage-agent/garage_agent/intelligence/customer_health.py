"""Deterministic customer health scoring."""

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from garage_agent.db.models import Booking, Customer, JobCard, Vehicle

COMPLETED_BOOKING_SCORE = 10
CANCELLED_BOOKING_SCORE = -20
COMPLETED_JOBCARD_SCORE = 5


def update_customer_health(db: Session, garage_id: int, customer_id: int) -> None:
    """Recompute and persist customer health score from current booking/job history."""
    customer = db.scalar(
        select(Customer)
        .where(Customer.id == customer_id)
        .where(Customer.garage_id == garage_id)
    )
    if customer is None:
        raise ValueError("Customer not found.")

    completed_bookings = db.scalar(
        select(func.count(Booking.id))
        .select_from(Booking)
        .join(
            Vehicle,
            and_(
                Booking.vehicle_id == Vehicle.id,
                Booking.garage_id == Vehicle.garage_id,
            ),
        )
        .where(Booking.garage_id == garage_id)
        .where(Vehicle.garage_id == garage_id)
        .where(Vehicle.customer_id == customer_id)
        .where(Booking.status == "COMPLETED")
    ) or 0

    cancelled_bookings = db.scalar(
        select(func.count(Booking.id))
        .select_from(Booking)
        .join(
            Vehicle,
            and_(
                Booking.vehicle_id == Vehicle.id,
                Booking.garage_id == Vehicle.garage_id,
            ),
        )
        .where(Booking.garage_id == garage_id)
        .where(Vehicle.garage_id == garage_id)
        .where(Vehicle.customer_id == customer_id)
        .where(Booking.status == "CANCELLED")
    ) or 0

    completed_job_cards = db.scalar(
        select(func.count(JobCard.id))
        .select_from(JobCard)
        .join(
            Booking,
            and_(
                JobCard.booking_id == Booking.id,
                JobCard.garage_id == Booking.garage_id,
            ),
        )
        .join(
            Vehicle,
            and_(
                Booking.vehicle_id == Vehicle.id,
                Booking.garage_id == Vehicle.garage_id,
            ),
        )
        .where(JobCard.garage_id == garage_id)
        .where(Booking.garage_id == garage_id)
        .where(Vehicle.garage_id == garage_id)
        .where(Vehicle.customer_id == customer_id)
        .where(JobCard.status == "COMPLETED")
    ) or 0

    customer.health_score = (
        int(completed_bookings) * COMPLETED_BOOKING_SCORE
        + int(cancelled_bookings) * CANCELLED_BOOKING_SCORE
        + int(completed_job_cards) * COMPLETED_JOBCARD_SCORE
    )
