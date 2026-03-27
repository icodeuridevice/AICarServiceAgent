"""Daily reminder scheduler for upcoming service bookings.

Uses APScheduler BackgroundScheduler to run a daily job at 09:00 AM
that fetches today's active bookings and sends WhatsApp reminders via Twilio.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from garage_agent.db.models import Booking, BookingReminder, Garage, Reminder, Vehicle, Customer
from garage_agent.db.session import SessionLocal
from garage_agent.services.predictive_reminder_service import (
    get_due_vehicles,
    mark_reminder_sent,
)
from garage_agent.services.slot_service import generate_daily_slots
from garage_agent.services.twilio_client import send_whatsapp_message

logger = logging.getLogger(__name__)


def _infer_service_type(db, vehicle) -> str:
    """Return service_type from the vehicle's last completed booking, or default."""
    last_booking = db.scalar(
        select(Booking)
        .where(Booking.vehicle_id == vehicle.id)
        .where(Booking.garage_id == vehicle.garage_id)
        .where(Booking.status == "COMPLETED")
        .order_by(Booking.service_date.desc())
    )
    if last_booking is not None:
        return last_booking.service_type
    return "general_service"


def _send_daily_reminders(garage_id: int) -> None:
    """Fetch today's active bookings and send WhatsApp reminders."""
    today = date.today()
    logger.info("Running daily reminder job for %s (garage_id=%s)", today, garage_id)

    db = SessionLocal()
    try:
        sent, failed = 0, 0
        garage = db.scalar(select(Garage).where(Garage.id == garage_id))
        if garage is None:
            logger.warning("Garage %s not found. Skipping reminder job.", garage_id)
            return

        bookings = db.scalars(
            select(Booking)
            .options(
                joinedload(Booking.vehicle).joinedload(Vehicle.customer),
            )
            .where(Booking.garage_id == garage_id)
            .where(Booking.service_date == today)
            .where(Booking.status == "CONFIRMED")
            .where(Booking.reminder_sent.is_(False))  # noqa: E712
        ).unique().all()

        total_candidates = len(bookings)
        for booking in bookings:
            customer: Customer | None = booking.vehicle.customer if booking.vehicle else None
            if customer is None or not customer.phone:
                logger.warning(
                    "Booking %d has no associated customer phone. Skipping.",
                    booking.id,
                )
                failed += 1
                continue

            message = (
                f"Reminder: Your {booking.service_type} is scheduled today "
                f"at {booking.service_time.strftime('%I:%M %p')}."
            )

            try:
                message_sid = send_whatsapp_message(to=customer.phone, body=message)
                booking.reminder_sent = True
                booking.reminder_sent_at = datetime.now(timezone.utc)
                booking.reminder_message_sid = message_sid
                db.commit()
                sent += 1
            except Exception:
                logger.exception(
                    "Failed to send reminder for booking %d to %s",
                    booking.id,
                    customer.phone,
                )
                failed += 1

        predictive_sent, predictive_failed = 0, 0
        due_vehicles = get_due_vehicles(db, garage_id=garage_id)
        for vehicle in due_vehicles:

            if vehicle.last_reminder_sent_at:
                continue

            customer: Customer | None = vehicle.customer
            if customer is None or not customer.phone:
                logger.warning(
                    "Vehicle %d has no associated customer phone. Skipping predictive reminder.",
                    vehicle.id,
                )
                predictive_failed += 1
                continue

            message = (
                f"Your vehicle is due for service on "
                f"{vehicle.next_service_date}. "
                "Reply YES to book your slot."
            )

            try:
                send_whatsapp_message(to=customer.phone, body=message)
                mark_reminder_sent(vehicle)

                # Store Reminder record for auto-booking on reply
                service_type = _infer_service_type(db, vehicle)
                db.add(Reminder(
                    garage_id=garage_id,
                    phone=customer.phone,
                    service_type=service_type,
                    predicted_date=vehicle.next_service_date,
                    status="SENT",
                ))

                predictive_sent += 1
            except Exception:
                logger.exception(
                    "Failed to send predictive reminder for vehicle %d to %s",
                    vehicle.id,
                    customer.phone,
                )
                predictive_failed += 1

        db.commit()

        logger.info(
            "Reminder job complete for garage_id=%s: %d sent, %d failed out of %d bookings.",
            garage_id,
            sent,
            failed,
            total_candidates,
        )
        logger.info(
            "Predictive reminder run for garage_id=%s: %d sent, %d failed out of %d due vehicles.",
            garage_id,
            predictive_sent,
            predictive_failed,
            len(due_vehicles),
        )
    except Exception:
        logger.exception("Unhandled error in reminder job.")
    finally:
        db.close()


def _build_booking_reminder_message(reminder, booking, vehicle) -> str:
    """Build a human-friendly WhatsApp reminder message."""
    brand = vehicle.brand or "your vehicle"
    model = vehicle.vehicle_model or ""
    vehicle_label = f"{brand} {model}".strip()

    if reminder.reminder_type == "24h":
        return (
            f"Reminder \U0001F697\n\n"
            f"Your {vehicle_label} service is scheduled tomorrow.\n\n"
            f"\U0001F4C5 {booking.service_date}\n"
            f"\u23F0 {booking.service_time.strftime('%I:%M %p')}"
        )

    # 2h reminder
    return (
        f"Reminder \u23F0\n\n"
        f"Your service is in 2 hours.\n\n"
        f"Vehicle: {vehicle_label}"
    )


def _process_booking_reminders(garage_id: int) -> None:
    """Send pending 24h / 2h booking reminders."""
    now = datetime.now(timezone.utc)
    logger.info(
        "Running booking reminder processor (garage_id=%s)",
        garage_id,
    )

    db = SessionLocal()
    try:
        reminders = db.scalars(
            select(BookingReminder)
            .where(BookingReminder.garage_id == garage_id)
            .where(BookingReminder.is_sent.is_(False))
            .where(BookingReminder.scheduled_time <= now)
        ).all()

        sent, skipped, failed = 0, 0, 0

        for reminder in reminders:
            booking = db.get(Booking, reminder.booking_id)
            if booking is None or booking.status == "CANCELLED":
                reminder.is_sent = True
                skipped += 1
                logger.info(
                    "event=reminder_skipped reason=cancelled_or_missing "
                    "booking_id=%s type=%s",
                    reminder.booking_id,
                    reminder.reminder_type,
                )
                continue

            vehicle = db.get(Vehicle, booking.vehicle_id)
            if vehicle is None:
                skipped += 1
                logger.warning(
                    "event=reminder_skipped reason=no_vehicle booking_id=%s",
                    reminder.booking_id,
                )
                continue

            customer: Customer | None = vehicle.customer
            if customer is None or not customer.phone:
                skipped += 1
                logger.warning(
                    "event=reminder_skipped reason=no_customer_phone "
                    "booking_id=%s",
                    reminder.booking_id,
                )
                continue

            message = _build_booking_reminder_message(reminder, booking, vehicle)

            try:
                send_whatsapp_message(to=customer.phone, body=message)
                reminder.is_sent = True
                sent += 1
                logger.info(
                    "event=reminder_sent booking_id=%s type=%s phone=%s",
                    reminder.booking_id,
                    reminder.reminder_type,
                    customer.phone,
                )
            except Exception:
                logger.exception(
                    "Failed to send booking reminder for booking %d",
                    reminder.booking_id,
                )
                failed += 1

        db.commit()

        logger.info(
            "Booking reminder processor done for garage_id=%s: "
            "sent=%d skipped=%d failed=%d total=%d",
            garage_id,
            sent,
            skipped,
            failed,
            len(reminders),
        )
    except Exception:
        logger.exception("Unhandled error in booking reminder processor.")
    finally:
        db.close()


def _generate_tomorrow_slots(garage_id: int) -> None:
    """Auto-generate time slots for the next day."""
    tomorrow = date.today() + timedelta(days=1)
    logger.info(
        "Running slot generation job for %s (garage_id=%s)",
        tomorrow,
        garage_id,
    )
    db = SessionLocal()
    try:
        created = generate_daily_slots(db=db, garage_id=garage_id, target_date=tomorrow)
        logger.info(
            "Slot generation complete: %d new slots for garage_id=%s on %s",
            created,
            garage_id,
            tomorrow,
        )
    except Exception:
        logger.exception("Unhandled error in slot generation job.")
    finally:
        db.close()


def start_scheduler(garage_id: int) -> BackgroundScheduler:
    """Create, configure, and start the background reminder scheduler.

    Returns the scheduler instance so the caller can shut it down if needed.
    """
    scheduler = BackgroundScheduler(daemon=True)

    # Slot generation at 08:00 — before the 09:00 reminder job
    scheduler.add_job(
        _generate_tomorrow_slots,
        trigger="cron",
        hour=8,
        minute=0,
        id="daily_slot_generation",
        name="Generate time slots for next day",
        replace_existing=True,
        kwargs={"garage_id": garage_id},
    )

    scheduler.add_job(
        _send_daily_reminders,
        trigger="cron",
        hour=9,
        minute=0,
        id="daily_booking_reminder",
        name="Send daily WhatsApp booking reminders",
        replace_existing=True,
        kwargs={"garage_id": garage_id},
    )

    scheduler.start()

    # Booking-reminder processor — runs every 5 minutes
    scheduler.add_job(
        _process_booking_reminders,
        trigger="interval",
        minutes=5,
        id="booking_reminder_processor",
        name="Process 24h / 2h booking reminders",
        replace_existing=True,
        kwargs={"garage_id": garage_id},
    )

    logger.info(
        "Reminder scheduler started for garage_id=%s "
        "(slot gen at 08:00, reminders at 09:00, booking reminders every 5m).",
        garage_id,
    )
    return scheduler
