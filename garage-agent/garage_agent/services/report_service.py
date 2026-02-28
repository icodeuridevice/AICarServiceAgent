"""Business logic for operational reporting."""

from datetime import date
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from garage_agent.db.models import Booking, JobCard


def get_daily_summary(
    db: Session,
    garage_id: int,
    target_date: date | None = None,
) -> dict:
    """Return operational summary for a given date."""
    if target_date is None:
        target_date = date.today()

    # Total bookings for the day
    total_bookings = db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(Booking.garage_id == garage_id)
        .where(Booking.service_date == target_date)
    ) or 0

    # Cancelled bookings for the day
    cancelled_bookings = db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.garage_id == garage_id,
            Booking.service_date == target_date,
            Booking.status == "CANCELLED",
        )
    ) or 0

    # Jobs currently in progress
    in_progress_jobs = db.scalar(
        select(func.count())
        .select_from(JobCard)
        .where(JobCard.garage_id == garage_id)
        .where(JobCard.status == "IN_PROGRESS")
    ) or 0

    # Jobs completed today
    completed_jobs = db.scalar(
        select(func.count())
        .select_from(JobCard)
        .where(
            JobCard.garage_id == garage_id,
            JobCard.status == "COMPLETED",
            func.date(JobCard.completed_at) == target_date,
        )
    ) or 0

    # Total revenue for completed jobs today
    total_revenue = db.scalar(
        select(func.sum(JobCard.total_cost))
        .where(
            JobCard.garage_id == garage_id,
            JobCard.status == "COMPLETED",
            JobCard.completed_at.is_not(None),
            func.date(JobCard.completed_at) == target_date,
        )
    )

    return {
        "date": str(target_date),
        "total_bookings": int(total_bookings),
        "in_progress_jobs": int(in_progress_jobs),
        "completed_jobs": int(completed_jobs),
        "cancelled_bookings": int(cancelled_bookings),
        "total_revenue": float(total_revenue or 0),
    }
