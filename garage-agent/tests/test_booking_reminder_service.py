"""Tests for the proactive booking reminder engine."""

from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from garage_agent.db.session import Base
from garage_agent.db.models import (
    Booking,
    BookingReminder,
    Customer,
    Garage,
    Vehicle,
)
from garage_agent.services.booking_reminder_service import (
    cancel_booking_reminders,
    schedule_booking_reminders,
)
from garage_agent.scheduler.reminder_scheduler import (
    _build_booking_reminder_message,
    _process_booking_reminders,
)


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    """In-memory SQLite session for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()

    # Seed a garage, customer, vehicle
    garage = Garage(id=1, name="Test Garage", whatsapp_number="whatsapp:+10000000000")
    session.add(garage)
    session.flush()

    customer = Customer(id=1, garage_id=1, phone="+1234567890")
    session.add(customer)
    session.flush()

    vehicle = Vehicle(
        id=1,
        customer_id=1,
        garage_id=1,
        brand="Toyota",
        vehicle_model="Corolla",
    )
    session.add(vehicle)
    session.flush()

    yield session
    session.close()


def _make_booking(db: Session, days_ahead: int = 2) -> Booking:
    """Helper to create a PENDING booking N days in the future."""
    future_date = date.today() + timedelta(days=days_ahead)
    booking = Booking(
        id=100,
        vehicle_id=1,
        garage_id=1,
        service_type="oil_change",
        service_date=future_date,
        service_time=time(10, 0),
        status="PENDING",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


# ── schedule_booking_reminders ────────────────────────────────────────

class TestScheduleBookingReminders:
    def test_creates_two_reminders_for_future_booking(self, db):
        booking = _make_booking(db, days_ahead=3)
        schedule_booking_reminders(db, booking)

        reminders = db.query(BookingReminder).all()
        assert len(reminders) == 2
        types = {r.reminder_type for r in reminders}
        assert types == {"24h", "2h"}
        assert all(r.is_sent is False for r in reminders)

    def test_skips_past_reminders(self, db):
        """A booking 1 hour from now should skip the 24h and 2h reminders."""
        past_date = date.today()
        booking = Booking(
            id=101,
            vehicle_id=1,
            garage_id=1,
            service_type="oil_change",
            service_date=past_date,
            service_time=(datetime.now(timezone.utc) + timedelta(hours=1)).time(),
            status="PENDING",
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

        schedule_booking_reminders(db, booking)
        reminders = db.query(BookingReminder).filter(
            BookingReminder.booking_id == 101
        ).all()
        # Both 24h and 2h are in the past for a booking 1h from now
        assert len(reminders) == 0

    def test_scheduled_time_values(self, db):
        booking = _make_booking(db, days_ahead=3)
        schedule_booking_reminders(db, booking)

        service_dt = datetime.combine(
            booking.service_date, booking.service_time, tzinfo=timezone.utc
        )
        reminders = sorted(
            db.query(BookingReminder).all(),
            key=lambda r: r.scheduled_time,
        )
        # 24h before comes earlier in the timeline than 2h before
        assert reminders[0].reminder_type == "24h"
        r_24h = reminders[0]
        r_2h = reminders[1]
        assert r_24h.scheduled_time == service_dt - timedelta(hours=24)
        assert r_2h.scheduled_time == service_dt - timedelta(hours=2)


# ── cancel_booking_reminders ──────────────────────────────────────────

class TestCancelBookingReminders:
    def test_marks_unsent_reminders(self, db):
        booking = _make_booking(db, days_ahead=3)
        schedule_booking_reminders(db, booking)

        cancelled = cancel_booking_reminders(db, booking.id)
        assert cancelled == 2

        reminders = db.query(BookingReminder).all()
        assert all(r.is_sent is True for r in reminders)

    def test_ignores_already_sent(self, db):
        booking = _make_booking(db, days_ahead=3)
        schedule_booking_reminders(db, booking)

        # Mark one as sent
        first = db.query(BookingReminder).first()
        first.is_sent = True
        db.commit()

        cancelled = cancel_booking_reminders(db, booking.id)
        assert cancelled == 1  # only the unsent one


# ── build_reminder_message ────────────────────────────────────────────

class TestBuildReminderMessage:
    def test_24h_message(self):
        reminder = MagicMock(reminder_type="24h")
        booking = MagicMock(
            service_date=date(2026, 4, 1),
            service_time=time(14, 30),
        )
        vehicle = MagicMock(brand="Toyota", vehicle_model="Corolla")

        msg = _build_booking_reminder_message(reminder, booking, vehicle)
        assert "Toyota Corolla" in msg
        assert "tomorrow" in msg
        assert "02:30 PM" in msg

    def test_2h_message(self):
        reminder = MagicMock(reminder_type="2h")
        booking = MagicMock()
        vehicle = MagicMock(brand="Honda", vehicle_model="Civic")

        msg = _build_booking_reminder_message(reminder, booking, vehicle)
        assert "Honda Civic" in msg
        assert "2 hours" in msg

    def test_missing_brand(self):
        reminder = MagicMock(reminder_type="24h")
        booking = MagicMock(
            service_date=date(2026, 4, 1),
            service_time=time(10, 0),
        )
        vehicle = MagicMock(brand=None, vehicle_model=None)

        msg = _build_booking_reminder_message(reminder, booking, vehicle)
        assert "your vehicle" in msg


# ── _process_booking_reminders ────────────────────────────────────────

class TestProcessBookingReminders:
    @patch("garage_agent.scheduler.reminder_scheduler.send_whatsapp_message")
    @patch("garage_agent.scheduler.reminder_scheduler.SessionLocal")
    def test_skips_cancelled_booking(self, mock_session_cls, mock_send):
        """Cancelled bookings should be skipped and marked as sent."""
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        reminder = MagicMock(
            booking_id=1,
            reminder_type="24h",
            is_sent=False,
        )
        mock_db.scalars.return_value.all.return_value = [reminder]

        cancelled_booking = MagicMock(status="CANCELLED")
        mock_db.get.return_value = cancelled_booking

        _process_booking_reminders(garage_id=1)

        assert reminder.is_sent is True
        mock_send.assert_not_called()
        mock_db.commit.assert_called()
