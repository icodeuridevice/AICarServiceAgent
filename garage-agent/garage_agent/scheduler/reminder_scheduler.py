"""Daily reminder scheduler for upcoming service bookings.

Uses APScheduler BackgroundScheduler to run a daily job at 09:00 AM
that fetches today's active bookings and sends WhatsApp reminders via Twilio.
"""

import logging
from datetime import date, datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from garage_agent.db.models import Booking, Reminder, Vehicle, Customer, Garage
from garage_agent.db.session import SessionLocal
from garage_agent.services.predictive_reminder_service import (
    get_due_vehicles,
    mark_reminder_sent,
)
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


def start_scheduler(garage_id: int) -> BackgroundScheduler:
    """Create, configure, and start the background reminder scheduler.

    Returns the scheduler instance so the caller can shut it down if needed.
    """
    scheduler = BackgroundScheduler(daemon=True)

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
    logger.info(
        "Reminder scheduler started for garage_id=%s (daily job at 09:00 AM).",
        garage_id,
    )
    return scheduler
