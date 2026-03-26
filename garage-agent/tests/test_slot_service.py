"""Unit tests for the slot management service."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from garage_agent.db.session import Base
from garage_agent.db.models import ServiceBay, TimeSlot
from garage_agent.services.slot_service import (
    generate_daily_slots,
    get_available_slot,
    get_nearby_available_slots,
    reserve_slot,
)

TEST_GARAGE_ID = 1
TEST_DATE = date(2026, 4, 1)


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


def _create_bays(db: Session, count: int = 2) -> list[ServiceBay]:
    bays = []
    for i in range(1, count + 1):
        bay = ServiceBay(
            garage_id=TEST_GARAGE_ID,
            name=f"Bay {i}",
            is_active=True,
        )
        db.add(bay)
        bays.append(bay)
    db.flush()
    return bays


# ──────────────────────────────────────────────
# generate_daily_slots
# ──────────────────────────────────────────────

def test_generate_daily_slots(db: Session):
    """Generates expected number of slots: 18 time labels × 2 bays = 36."""
    _create_bays(db, count=2)
    created = generate_daily_slots(db, TEST_GARAGE_ID, TEST_DATE)
    assert created == 36  # 18 half-hours × 2 bays


def test_generate_daily_slots_no_duplicates(db: Session):
    """Second run should create zero additional slots (idempotent)."""
    _create_bays(db, count=2)
    generate_daily_slots(db, TEST_GARAGE_ID, TEST_DATE)
    second_run = generate_daily_slots(db, TEST_GARAGE_ID, TEST_DATE)
    assert second_run == 0


def test_generate_daily_slots_no_bays(db: Session):
    """No bays configured → returns 0 and does not crash."""
    created = generate_daily_slots(db, TEST_GARAGE_ID, TEST_DATE)
    assert created == 0


# ──────────────────────────────────────────────
# get_available_slot
# ──────────────────────────────────────────────

def test_get_available_slot_found(db: Session):
    _create_bays(db, count=1)
    generate_daily_slots(db, TEST_GARAGE_ID, TEST_DATE)
    slot = get_available_slot(db, TEST_GARAGE_ID, TEST_DATE, "09:00")
    assert slot is not None
    assert slot.service_time == "09:00"
    assert slot.is_booked is False


def test_get_available_slot_none_when_all_booked(db: Session):
    _create_bays(db, count=1)
    generate_daily_slots(db, TEST_GARAGE_ID, TEST_DATE)
    # Book all 09:00 slots (just one bay)
    slot = get_available_slot(db, TEST_GARAGE_ID, TEST_DATE, "09:00")
    assert slot is not None
    reserve_slot(db, slot)
    # Now should be None
    slot2 = get_available_slot(db, TEST_GARAGE_ID, TEST_DATE, "09:00")
    assert slot2 is None


# ──────────────────────────────────────────────
# get_nearby_available_slots
# ──────────────────────────────────────────────

def test_get_nearby_available_slots(db: Session):
    _create_bays(db, count=1)
    generate_daily_slots(db, TEST_GARAGE_ID, TEST_DATE)
    # Book the 09:00 slot
    slot_0900 = get_available_slot(db, TEST_GARAGE_ID, TEST_DATE, "09:00")
    assert slot_0900 is not None
    reserve_slot(db, slot_0900)

    alternatives = get_nearby_available_slots(
        db, TEST_GARAGE_ID, TEST_DATE, "09:00", limit=3,
    )
    assert len(alternatives) == 3
    # Should not contain the booked time
    assert "09:00" not in alternatives
    # First alternative should be 09:30
    assert alternatives[0] == "09:30"


# ──────────────────────────────────────────────
# reserve_slot
# ──────────────────────────────────────────────

def test_reserve_slot(db: Session):
    _create_bays(db, count=1)
    generate_daily_slots(db, TEST_GARAGE_ID, TEST_DATE)
    slot = get_available_slot(db, TEST_GARAGE_ID, TEST_DATE, "10:00")
    assert slot is not None
    reserve_slot(db, slot)
    assert slot.is_booked is True
