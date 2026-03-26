"""
Natural language date & time parser service.

Uses the ``dateparser`` library to convert expressions such as
"tomorrow", "today 4pm", and "next monday 10am" into concrete
``datetime.date`` and ``datetime.time`` objects.

This is a *pure parsing* layer — no database access, no side-effects.
"""

import logging
from datetime import datetime, time

import dateparser

logger = logging.getLogger(__name__)


def parse_natural_datetime(text: str) -> tuple:
    """Convert natural language into ``(date, time)`` or ``(None, None)``.

    Examples::

        >>> parse_natural_datetime("tomorrow")
        (datetime.date(2026, 3, 27), None)

        >>> parse_natural_datetime("today 4pm")
        (datetime.date(2026, 3, 26), datetime.time(16, 0))

        >>> parse_natural_datetime("next monday 10am")
        (datetime.date(2026, 3, 30), datetime.time(10, 0))

    When the input contains only a date phrase (e.g. "tomorrow") without
    an explicit time component, the function returns ``None`` for the time
    so the caller can ask the user for a time preference.

    Returns:
        A ``(date | None, time | None)`` tuple.
    """
    if not text or not text.strip():
        return None, None

    dt = dateparser.parse(
        text,
        settings={
            "PREFER_DATES_FROM": "future",
        },
    )

    if not dt:
        return None, None

    parsed_date = dt.date()

    # Detect whether the user actually specified a time.
    # dateparser defaults to the *current* time when no time token is
    # present, so we check whether common time indicators appear in the
    # original text.  If they don't, we treat time as unspecified.
    _TIME_INDICATORS = (
        "am", "pm", "morning", "afternoon", "evening", "night",
        "noon", "midnight", ":", "o'clock",
    )
    text_lower = text.lower()
    has_explicit_time = any(indicator in text_lower for indicator in _TIME_INDICATORS)

    parsed_time = dt.time() if has_explicit_time else None

    logger.info(
        "event=natural_date_parsed input=%r date=%s time=%s",
        text,
        parsed_date,
        parsed_time,
    )

    return parsed_date, parsed_time
