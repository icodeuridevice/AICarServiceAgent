"""Unit tests for the vehicle persistence service."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from garage_agent.db.session import Base
from garage_agent.db.models import Customer, Vehicle
from garage_agent.services.vehicle_service import get_or_create_vehicle

TEST_GARAGE_ID = 1


@pytest.fixture()
def db():
    """Provide a fresh in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


def _create_customer(db: Session, phone: str = "+1234567890") -> Customer:
    from garage_agent.db.models import Garage

    garage = Garage(
        id=TEST_GARAGE_ID,
        name="Test Garage",
        whatsapp_number="+0000000000",
    )
    db.add(garage)
    db.flush()

    customer = Customer(phone=phone, garage_id=TEST_GARAGE_ID)
    db.add(customer)
    db.flush()
    return customer


# ──────────────────────────────────────────────
# get_or_create_vehicle
# ──────────────────────────────────────────────


class TestGetOrCreateVehicle:
    def test_creates_vehicle_when_none_exists(self, db: Session):
        customer = _create_customer(db)
        vehicle = get_or_create_vehicle(
            db=db,
            garage_id=TEST_GARAGE_ID,
            customer_id=customer.id,
            brand="mercedes",
        )

        assert vehicle.id is not None
        assert vehicle.brand == "mercedes"
        assert vehicle.vehicle_model is None
        assert vehicle.customer_id == customer.id
        assert vehicle.garage_id == TEST_GARAGE_ID

    def test_returns_existing_vehicle_on_second_call(self, db: Session):
        customer = _create_customer(db)
        v1 = get_or_create_vehicle(
            db=db,
            garage_id=TEST_GARAGE_ID,
            customer_id=customer.id,
            brand="bmw",
            model="x5",
        )
        v2 = get_or_create_vehicle(
            db=db,
            garage_id=TEST_GARAGE_ID,
            customer_id=customer.id,
            brand="bmw",
            model="x5",
        )
        assert v1.id == v2.id

    def test_different_brands_create_separate_vehicles(self, db: Session):
        customer = _create_customer(db)
        v1 = get_or_create_vehicle(
            db=db,
            garage_id=TEST_GARAGE_ID,
            customer_id=customer.id,
            brand="bmw",
        )
        v2 = get_or_create_vehicle(
            db=db,
            garage_id=TEST_GARAGE_ID,
            customer_id=customer.id,
            brand="audi",
        )
        assert v1.id != v2.id

    def test_different_models_create_separate_vehicles(self, db: Session):
        customer = _create_customer(db)
        v1 = get_or_create_vehicle(
            db=db,
            garage_id=TEST_GARAGE_ID,
            customer_id=customer.id,
            brand="mercedes",
            model="c class",
        )
        v2 = get_or_create_vehicle(
            db=db,
            garage_id=TEST_GARAGE_ID,
            customer_id=customer.id,
            brand="mercedes",
            model="maybach s680",
        )
        assert v1.id != v2.id

    def test_model_none_works(self, db: Session):
        customer = _create_customer(db)
        vehicle = get_or_create_vehicle(
            db=db,
            garage_id=TEST_GARAGE_ID,
            customer_id=customer.id,
            brand="toyota",
            model=None,
        )
        assert vehicle.brand == "toyota"
        assert vehicle.vehicle_model is None

    def test_model_none_vs_model_string_are_separate(self, db: Session):
        customer = _create_customer(db)
        v1 = get_or_create_vehicle(
            db=db,
            garage_id=TEST_GARAGE_ID,
            customer_id=customer.id,
            brand="honda",
            model=None,
        )
        v2 = get_or_create_vehicle(
            db=db,
            garage_id=TEST_GARAGE_ID,
            customer_id=customer.id,
            brand="honda",
            model="civic",
        )
        assert v1.id != v2.id
