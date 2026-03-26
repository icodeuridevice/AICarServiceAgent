"""Vehicle persistence service."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from garage_agent.db.models import Vehicle

logger = logging.getLogger(__name__)


def get_or_create_vehicle(
    db: Session,
    garage_id: int,
    customer_id: int,
    brand: str,
    model: str | None = None,
) -> Vehicle:
    """Look up a vehicle by garage/customer/brand/model; create if missing.

    Returns the existing or newly-created ``Vehicle`` instance.
    """
    query = (
        select(Vehicle)
        .where(Vehicle.garage_id == garage_id)
        .where(Vehicle.customer_id == customer_id)
        .where(Vehicle.brand == brand)
    )
    if model is not None:
        query = query.where(Vehicle.vehicle_model == model)
    else:
        query = query.where(Vehicle.vehicle_model.is_(None))

    vehicle = db.scalar(query)

    if vehicle is not None:
        logger.info(
            "event=vehicle_resolved vehicle_id=%s brand=%s model=%s",
            vehicle.id,
            brand,
            model,
        )
        return vehicle

    vehicle = Vehicle(
        garage_id=garage_id,
        customer_id=customer_id,
        brand=brand,
        vehicle_model=model,
    )
    db.add(vehicle)
    db.flush()

    logger.info(
        "event=vehicle_created vehicle_id=%s brand=%s model=%s customer_id=%s",
        vehicle.id,
        brand,
        model,
        customer_id,
    )
    return vehicle
