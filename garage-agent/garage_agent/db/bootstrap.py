"""Bootstrap helpers for garage tenancy defaults."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from garage_agent.db.models import Garage

DEFAULT_GARAGE_NAME = "Default Garage"


def get_default_garage(db: Session) -> Garage:
    garage = db.scalar(select(Garage).order_by(Garage.id.asc()))
    if garage is not None:
        return garage

    garage = Garage(
        name=DEFAULT_GARAGE_NAME,
        phone=None,
    )
    db.add(garage)
    db.commit()
    db.refresh(garage)
    return garage
