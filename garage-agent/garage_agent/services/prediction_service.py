"""Service-date prediction utilities based on completed service history."""

from datetime import date, timedelta
from typing import TypedDict

from sqlalchemy.orm import Session

from garage_agent.services.intelligence_service import get_vehicle_completed_services


class ServiceDatePrediction(TypedDict):
    """Predicted next-service payload for a vehicle."""

    last_service_date: date
    predicted_next_service_date: date
    interval_days: int
    confidence: float


def _calculate_average_interval_days(service_dates: list[date]) -> int:
    """Return the average day gap between consecutive service dates."""
    gaps = [
        (current - previous).days
        for previous, current in zip(service_dates, service_dates[1:])
    ]
    return int(round(sum(gaps) / len(gaps)))


def predict_next_service_date(db: Session, vehicle_id: int, garage_id: int) -> ServiceDatePrediction:
    """Predict the next service date using completed service history.

    Rules:
    - No completed services raises ``ValueError``.
    - One completed service uses a default 90-day interval with 0.4 confidence.
    - Two or more completed services use average historical gap in days.
      Confidence is 0.7 for exactly two services, otherwise 0.9.

    Args:
        db: SQLAlchemy database session.
        vehicle_id: Target vehicle identifier.
        garage_id: Garage scope for isolation.

    Returns:
        Prediction payload with last service date, predicted next date,
        interval in days, and confidence score.

    Raises:
        ValueError: If no completed services are found for the vehicle.
    """
    completed_services = get_vehicle_completed_services(db=db, vehicle_id=vehicle_id, garage_id=garage_id)
    if not completed_services:
        raise ValueError("No completed services found for the vehicle.")

    sorted_services = sorted(completed_services, key=lambda item: item["service_date"])
    service_dates = [item["service_date"] for item in sorted_services]

    last_service_date = service_dates[-1]

    if len(service_dates) == 1:
        interval_days = 90
        confidence = 0.4
    else:
        interval_days = _calculate_average_interval_days(service_dates)
        confidence = 0.7 if len(service_dates) == 2 else 0.9

    predicted_date = last_service_date + timedelta(days=interval_days)

    return {
        "last_service_date": last_service_date,
        "predicted_next_service_date": predicted_date,
        "interval_days": interval_days,
        "confidence": confidence,
    }
