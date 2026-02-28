"""JobCard API routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from garage_agent.db.bootstrap import resolve_default_garage_context
from garage_agent.db.session import get_db
from garage_agent.services.jobcard_service import (
    create_job_card,
    update_job_card,
    complete_job_card,
    get_job_card_by_booking,
    list_active_job_cards,
)

router = APIRouter(prefix="/jobcards", tags=["JobCards"])


def _resolve_route_garage_id(db: Session) -> int:
    return resolve_default_garage_context(db=db).garage_id


@router.post("/")
def api_create_job_card(
    booking_id: int,
    technician_name: str | None = None,
    db: Session = Depends(get_db),
):
    garage_id = _resolve_route_garage_id(db=db)
    try:
        job = create_job_card(
            db=db,
            booking_id=booking_id,
            technician_name=technician_name,
            garage_id=garage_id,
        )
        return {"jobcard_id": job.id, "status": job.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{jobcard_id}")
def api_update_job_card(
    jobcard_id: int,
    technician_name: str | None = None,
    work_notes: str | None = None,
    total_cost: float | None = None,
    db: Session = Depends(get_db),
):
    garage_id = _resolve_route_garage_id(db=db)
    try:
        job = update_job_card(
            db=db,
            jobcard_id=jobcard_id,
            technician_name=technician_name,
            work_notes=work_notes,
            total_cost=total_cost,
            garage_id=garage_id,
        )
        return {"jobcard_id": job.id, "status": job.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{jobcard_id}/complete")
def api_complete_job_card(
    jobcard_id: int,
    db: Session = Depends(get_db),
):
    garage_id = _resolve_route_garage_id(db=db)
    try:
        job = complete_job_card(
            db=db,
            jobcard_id=jobcard_id,
            garage_id=garage_id,
        )
        return {"jobcard_id": job.id, "status": job.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/active")
def api_list_active_job_cards(
    db: Session = Depends(get_db),
):
    garage_id = _resolve_route_garage_id(db=db)
    jobs = list_active_job_cards(db=db, garage_id=garage_id)
    return [
        {
            "id": job.id,
            "booking_id": job.booking_id,
            "technician_name": job.technician_name,
            "started_at": job.started_at,
        }
        for job in jobs
    ]


@router.get("/booking/{booking_id}")
def api_get_job_by_booking(
    booking_id: int,
    db: Session = Depends(get_db),
):
    garage_id = _resolve_route_garage_id(db=db)
    job = get_job_card_by_booking(
        db=db,
        booking_id=booking_id,
        garage_id=garage_id,
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job card not found.")
    return {
        "id": job.id,
        "status": job.status,
        "technician_name": job.technician_name,
        "total_cost": job.total_cost,
    }
