"""Business logic for JobCard operations."""

from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from garage_agent.db.models import Booking, JobCard
from garage_agent.intelligence.customer_health import update_customer_health
from garage_agent.intelligence.service_prediction import calculate_next_service


def create_job_card(
    db: Session,
    booking_id: int,
    technician_name: str | None = None,
    *,
    garage_id: int,
) -> JobCard:
    """Create a job card for a booking and move booking to IN_PROGRESS."""
    booking = db.scalar(
        select(Booking)
        .where(Booking.id == booking_id)
        .where(Booking.garage_id == garage_id)
    )
    if booking is None:
        raise ValueError("Booking not found.")

    if booking.garage_id != garage_id:
        raise ValueError("Booking not found.")

    if booking.status in ("CANCELLED", "COMPLETED"):
        raise ValueError("Cannot create job card for this booking status.")

    if booking.job_card is not None:
        raise ValueError("Job card already exists for this booking.")

    job = JobCard(
        booking_id=booking_id,
        garage_id=garage_id,
        technician_name=technician_name,
        status="IN_PROGRESS",
    )

    booking.status = "IN_PROGRESS"

    db.add(job)
    db.commit()
    db.refresh(job)

    return job


def update_job_card(
    db: Session,
    jobcard_id: int,
    technician_name: str | None = None,
    work_notes: str | None = None,
    total_cost: float | None = None,
    *,
    garage_id: int,
) -> JobCard:
    """Update technician info, notes, or cost."""
    job = db.scalar(
        select(JobCard)
        .where(JobCard.id == jobcard_id)
        .where(JobCard.garage_id == garage_id)
    )
    if job is None:
        raise ValueError("Job card not found.")

    if technician_name is not None:
        job.technician_name = technician_name

    if work_notes is not None:
        job.work_notes = work_notes

    if total_cost is not None:
        job.total_cost = total_cost

    db.commit()
    db.refresh(job)

    return job


def complete_job_card(db: Session, jobcard_id: int, *, garage_id: int) -> JobCard:
    """Mark job card and booking as completed."""
    job = db.scalar(
        select(JobCard)
        .where(JobCard.id == jobcard_id)
        .where(JobCard.garage_id == garage_id)
    )
    if job is None:
        raise ValueError("Job card not found.")

    if job.status == "COMPLETED":
        raise ValueError("Job card already completed.")

    job.status = "COMPLETED"
    job.completed_at = datetime.now(timezone.utc)

    booking = job.booking
    if booking is None or booking.garage_id != garage_id:
        raise ValueError("Booking not found.")

    if booking.vehicle is None:
        raise ValueError("Booking vehicle not found.")

    booking.status = "COMPLETED"
    booking.vehicle.next_service_due_date = calculate_next_service(
        service_type=booking.service_type,
        service_date=booking.service_date,
    )
    update_customer_health(
        db=db,
        garage_id=garage_id,
        customer_id=booking.vehicle.customer_id,
    )

    db.commit()
    db.refresh(job)

    return job


def get_job_card_by_booking(db: Session, booking_id: int, *, garage_id: int) -> JobCard | None:
    """Return job card for a booking."""
    return db.scalar(
        select(JobCard)
        .where(JobCard.booking_id == booking_id)
        .where(JobCard.garage_id == garage_id)
    )


def list_active_job_cards(db: Session, *, garage_id: int) -> List[JobCard]:
    """Return all job cards currently in progress."""
    return db.scalars(
        select(JobCard)
        .where(JobCard.status == "IN_PROGRESS")
        .where(JobCard.garage_id == garage_id)
    ).all()
