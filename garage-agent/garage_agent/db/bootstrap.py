"""Bootstrap helpers for garage tenancy defaults."""

import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from garage_agent.db.models import Customer, Garage

DEFAULT_GARAGE_NAME = "Default Garage"
DEFAULT_GARAGE_WHATSAPP_NUMBER = os.getenv(
    "DEFAULT_GARAGE_WHATSAPP_NUMBER",
    "whatsapp:+10000000000",
)


@dataclass(frozen=True)
class GarageContext:
    garage_id: int


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


def resolve_default_garage_context(db: Session) -> GarageContext:
    garage = get_default_garage(db)
    return GarageContext(garage_id=garage.id)


def resolve_garage_from_phone(db: Session, phone: str | None) -> GarageContext:
    normalized_phone = (phone or "").replace("whatsapp:", "").strip()
    if normalized_phone:
        garage_id = db.scalar(
            select(Customer.garage_id)
            .where(Customer.phone == normalized_phone)
            .order_by(Customer.id.desc())
        )
        if garage_id is not None:
            return GarageContext(garage_id=int(garage_id))

    return resolve_default_garage_context(db)
