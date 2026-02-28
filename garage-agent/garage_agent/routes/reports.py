"""Operational reporting routes."""

from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from garage_agent.db.bootstrap import resolve_default_garage_context
from garage_agent.db.session import SessionLocal
from garage_agent.services.report_service import get_daily_summary


router = APIRouter(prefix="/reports", tags=["Reports"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/daily")
def daily_report(
    report_date: date | None = Query(
        default=None,
        description="Date in YYYY-MM-DD format",
    ),
    db: Session = Depends(get_db),
):
    garage_id = resolve_default_garage_context(db=db).garage_id
    return get_daily_summary(
        db=db,
        garage_id=garage_id,
        target_date=report_date,
    )
