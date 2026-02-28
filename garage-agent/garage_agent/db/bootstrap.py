"""Bootstrap helpers for garage tenancy defaults."""

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from garage_agent.db.models import Garage

DEFAULT_GARAGE_NAME = "Default Garage"
DEFAULT_GARAGE_WHATSAPP_NUMBER = os.getenv(
    "DEFAULT_GARAGE_WHATSAPP_NUMBER",
    "whatsapp:+10000000000",
)


def _build_unique_default_whatsapp_number(db: Session) -> str:
    base_number = DEFAULT_GARAGE_WHATSAPP_NUMBER
    candidate = base_number
    suffix = 1
    while db.scalar(select(Garage.id).where(Garage.whatsapp_number == candidate)) is not None:
        suffix += 1
        candidate = f"{base_number}-{suffix}"
    return candidate


def get_default_garage(db: Session) -> Garage:
    garage = db.scalar(select(Garage).order_by(Garage.id.asc()))
    if garage is not None:
        if not garage.whatsapp_number:
            garage.whatsapp_number = _build_unique_default_whatsapp_number(db)
            db.commit()
            db.refresh(garage)
        return garage

    garage = Garage(
        name=DEFAULT_GARAGE_NAME,
        phone=None,
        whatsapp_number=_build_unique_default_whatsapp_number(db),
    )
    db.add(garage)
    db.commit()
    db.refresh(garage)
    return garage
