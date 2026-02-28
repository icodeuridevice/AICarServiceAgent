"""
JobCard tools exposed to AI layer.

These wrap jobcard service logic safely.
"""

from sqlalchemy.orm import Session

from garage_agent.services.jobcard_service import (
    create_job_card,
    complete_job_card,
    update_job_card,
    get_job_card_by_booking,
)


def tool_create_jobcard(
    db: Session,
    garage_id: int,
    booking_id: int,
    technician_name: str | None = None,
):
    return create_job_card(
        db=db,
        garage_id=garage_id,
        booking_id=booking_id,
        technician_name=technician_name,
    )


def tool_complete_jobcard(
    db: Session,
    garage_id: int,
    jobcard_id: int,
):
    return complete_job_card(
        db=db,
        garage_id=garage_id,
        jobcard_id=jobcard_id,
    )


def tool_update_jobcard(
    db: Session,
    garage_id: int,
    jobcard_id: int,
    technician_name: str | None = None,
    work_notes: str | None = None,
    total_cost: float | None = None,
):
    return update_job_card(
        db=db,
        garage_id=garage_id,
        jobcard_id=jobcard_id,
        technician_name=technician_name,
        work_notes=work_notes,
        total_cost=total_cost,
    )


def tool_get_jobcard_by_booking(
    db: Session,
    garage_id: int,
    booking_id: int,
):
    return get_job_card_by_booking(
        db=db,
        garage_id=garage_id,
        booking_id=booking_id,
    )
