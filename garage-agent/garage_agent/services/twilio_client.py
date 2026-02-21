"""Twilio client configuration for WhatsApp messaging."""

import os
import logging
from dotenv import load_dotenv
from twilio.rest import Client

# Load environment variables from .env (for local development)
load_dotenv()

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv(
    "TWILIO_WHATSAPP_FROM",
    "whatsapp:+14155238886",  # Twilio Sandbox default
)

if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
    logger.warning(
        "Twilio credentials not set. WhatsApp messaging will fail at runtime."
    )

client: Client | None = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def send_whatsapp_message(to: str, body: str) -> str:
    """Send a WhatsApp message via Twilio and return the message SID."""
    if client is None:
        raise RuntimeError("Twilio client is not configured.")

    if not to.startswith("+"):
        raise ValueError("Phone number must be in E.164 format.")

    message = client.messages.create(
        from_=TWILIO_WHATSAPP_FROM,
        to=f"whatsapp:{to}",
        body=body,
        status_callback="https://dulcie-unreported-winterly.ngrok-free.dev/twilio/status",
    )

    logger.info("WhatsApp message sent to %s (SID: %s)", to, message.sid)
    return message.sid