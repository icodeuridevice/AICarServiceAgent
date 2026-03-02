import logging

from garage_agent.core.config import STAFF_ALERT_PHONE
from garage_agent.services.whatsapp_service import send_whatsapp_message

logger = logging.getLogger(__name__)


def notify_staff_escalation(
    vehicle_id: int,
    health_score: int,
    reason: str,
) -> None:
    if not STAFF_ALERT_PHONE:
        logger.warning("STAFF_ALERT_PHONE not configured.")
        return

    try:
        message = (
            "\u26A0\uFE0F ESCALATION ALERT\n"
            f"Vehicle ID: {vehicle_id}\n"
            f"Health Score: {health_score}\n"
            f"Reason: {reason}"
        )

        send_whatsapp_message(
            to=STAFF_ALERT_PHONE,
            body=message,
        )
    except Exception as e:
        logger.error("Failed to send escalation alert: %s", e)
