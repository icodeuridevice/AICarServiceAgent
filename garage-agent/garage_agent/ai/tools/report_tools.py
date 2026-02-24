"""
Reporting tools exposed to AI layer.
"""

from datetime import date
from sqlalchemy.orm import Session

from garage_agent.services.report_service import get_daily_summary


def tool_get_daily_summary(
    db: Session,
    target_date: date | None = None,
):
    """
    Returns booking + revenue summary for a given date.
    If no date provided → defaults to today.
    """
    return get_daily_summary(
        db=db,
        target_date=target_date or date.today(),
    )