"""Read-only intelligence data helpers for vehicle service history."""

from datetime import date, datetime, time
from typing import TypedDict

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from garage_agent.db.models import Booking, JobCard, Vehicle


class VehicleServiceHistoryItem(TypedDict):
    """Detailed completed service entry for a vehicle."""

    booking_id: int
    service_type: str
    service_date: date
    service_time: time
    technician_name: str | None
    total_cost: float | None
    completed_at: datetime | None


class VehicleCompletedServiceItem(TypedDict):
    """Simplified completed service entry for downstream intelligence."""

    service_type: str
    service_date: date
    total_cost: float | None


def _ensure_vehicle_exists(db: Session, vehicle_id: int) -> None:
    """Validate that the target vehicle exists before querying history."""
    vehicle_exists = db.scalar(
        select(Vehicle.id).where(Vehicle.id == vehicle_id).limit(1)
    )
    if vehicle_exists is None:
        raise ValueError("Vehicle not found.")


def get_vehicle_service_history(
    db: Session,
    vehicle_id: int,
) -> list[VehicleServiceHistoryItem]:
    """Return all completed job-card-backed services for a vehicle, oldest first.

    The result is built from a read-only join between bookings and job cards.

    Raises:
        ValueError: If the vehicle does not exist.
    """
    _ensure_vehicle_exists(db=db, vehicle_id=vehicle_id)

    history_query = (
        select(
            Booking.id.label("booking_id"),
            Booking.service_type.label("service_type"),
            Booking.service_date.label("service_date"),
            Booking.service_time.label("service_time"),
            JobCard.technician_name.label("technician_name"),
            JobCard.total_cost.label("total_cost"),
            JobCard.completed_at.label("completed_at"),
        )
        .select_from(Booking)
        .join(
            JobCard,
            and_(
                JobCard.booking_id == Booking.id,
                JobCard.garage_id == Booking.garage_id,
            ),
        )
        .where(Booking.vehicle_id == vehicle_id)
        .where(Booking.status == "COMPLETED")
        .order_by(
            Booking.service_date.asc(),
            Booking.service_time.asc(),
            Booking.id.asc(),
        )
    )

    rows = db.execute(history_query).all()
    history: list[VehicleServiceHistoryItem] = []
    for row in rows:
        record = row._mapping
        history.append(
            {
                "booking_id": int(record["booking_id"]),
                "service_type": record["service_type"],
                "service_date": record["service_date"],
                "service_time": record["service_time"],
                "technician_name": record["technician_name"],
                "total_cost": (
                    float(record["total_cost"])
                    if record["total_cost"] is not None
                    else None
                ),
                "completed_at": record["completed_at"],
            }
        )
    return history


def get_vehicle_completed_services(
    db: Session,
    vehicle_id: int,
) -> list[VehicleCompletedServiceItem]:
    """Return a minimal completed-service view for intelligence consumers.

    Raises:
        ValueError: If the vehicle does not exist.
    """
    history = get_vehicle_service_history(db=db, vehicle_id=vehicle_id)
    return [
        {
            "service_type": item["service_type"],
            "service_date": item["service_date"],
            "total_cost": item["total_cost"],
        }
        for item in history
    ]
