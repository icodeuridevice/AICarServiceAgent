"""Utilities for extracting structured booking details from free-text messages."""

import re

DATE_PATTERN = re.compile(r"\b([0-3]?\d/[0-1]?\d)\b")


def extract_booking_details(message: str) -> dict[str, str | None]:
    """Extract service type and service date from a customer message."""
    normalized_message = message.lower()

    if "oil" in normalized_message:
        service_type = "oil_change"
    elif "service" in normalized_message:
        service_type = "service"
    elif "repair" in normalized_message:
        service_type = "repair"
    else:
        service_type = "general_service"

    if "today" in normalized_message:
        service_date: str | None = "today"
    elif "tomorrow" in normalized_message:
        service_date = "tomorrow"
    else:
        date_match = DATE_PATTERN.search(normalized_message)
        service_date = date_match.group(1) if date_match else None

    return {
        "service_type": service_type,
        "service_date": service_date,
    }
