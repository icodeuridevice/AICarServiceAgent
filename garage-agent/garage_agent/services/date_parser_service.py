"""
Natural language date & time parser service.

Uses the ``dateparser`` library to convert expressions such as
"tomorrow", "today 4pm", and "next monday 10am" into concrete
``datetime.date`` and ``datetime.time`` objects.

This is a *pure parsing* layer — no database access, no side-effects.
"""

import logging
import re
from datetime import date, datetime, time, timedelta

import dateparser

logger = logging.getLogger(__name__)

_TIME_OF_DAY_DEFAULTS = {
    "morning": time(9, 0),
    "afternoon": time(15, 0),
    "evening": time(18, 0),
    "night": time(20, 0),
    "noon": time(12, 0),
    "midnight": time(0, 0),
}

_WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_MONTH_KEYWORDS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)

_DATE_KEYWORDS = (
    "today",
    "tomorrow",
    "day after tomorrow",
    "next ",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)

_DATE_PATTERNS = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
)

_TIME_PATTERNS = (
    re.compile(r"\b\d{1,2}:\d{2}\s*(?:am|pm)?\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}\s*(?:am|pm)\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}\s*o'clock\b", re.IGNORECASE),
)


def _utc_today() -> date:
    return datetime.utcnow().date()


def _contains_explicit_date(text: str) -> bool:
    lowered = text.lower()
    if any(keyword in lowered for keyword in _DATE_KEYWORDS):
        return True
    return any(pattern.search(text) for pattern in _DATE_PATTERNS)


def _contains_explicit_time(text: str) -> bool:
    lowered = text.lower()
    if any(keyword in lowered for keyword in _TIME_OF_DAY_DEFAULTS):
        return True
    return any(pattern.search(text) for pattern in _TIME_PATTERNS)


def _extract_date(text: str) -> date | None:
    lowered = text.lower()
    normalized = lowered.strip()
    today = _utc_today()

    if normalized == "day after tomorrow":
        return today + timedelta(days=2)
    if normalized == "tomorrow":
        return today + timedelta(days=1)
    if normalized == "today":
        return today

    if re.search(r"\bday after tomorrow\b", lowered):
        return today + timedelta(days=2)
    if re.search(r"\btomorrow\b", lowered):
        return today + timedelta(days=1)
    if re.search(r"\btoday\b", lowered):
        return today

    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        raw_date = match.group(0)
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
            try:
                return datetime.strptime(raw_date, fmt).date()
            except ValueError:
                continue

    weekday_match = re.search(
        r"\b(?:next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        lowered,
    )
    if weekday_match:
        target_weekday = _WEEKDAY_INDEX[weekday_match.group(1)]
        delta = (target_weekday - today.weekday()) % 7
        if delta == 0:
            delta = 7
        return today + timedelta(days=delta)

    if any(month in lowered for month in _MONTH_KEYWORDS):
        parsed = dateparser.parse(
            text,
            settings={"PREFER_DATES_FROM": "future"},
        )
        if parsed:
            return parsed.date()

    return None


def _extract_time(text: str) -> time | None:
    lowered = text.lower()
    for label, mapped_time in _TIME_OF_DAY_DEFAULTS.items():
        if label in lowered:
            return mapped_time

    am_pm_match = re.search(
        r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
        text,
        re.IGNORECASE,
    )
    if am_pm_match:
        hour = int(am_pm_match.group(1))
        minute = int(am_pm_match.group(2) or "0")
        meridiem = am_pm_match.group(3).lower()
        if 1 <= hour <= 12 and 0 <= minute <= 59:
            if meridiem == "am":
                hour = 0 if hour == 12 else hour
            else:
                hour = 12 if hour == 12 else hour + 12
            return time(hour, minute)

    twenty_four_match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if twenty_four_match:
        hour = int(twenty_four_match.group(1))
        minute = int(twenty_four_match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute)

    oclock_match = re.search(r"\b(\d{1,2})\s*o'clock\b", text, re.IGNORECASE)
    if oclock_match:
        hour = int(oclock_match.group(1))
        if 0 <= hour <= 23:
            return time(hour, 0)

    return None


def parse_natural_datetime(text: str) -> tuple:
    """Convert natural language into ``(date, time)`` or ``(None, None)``.

    When the input contains only a date phrase (e.g. "tomorrow") without
    an explicit time component, the function returns ``None`` for the time
    so the caller can ask the user for a time preference.

    Returns:
        A ``(date | None, time | None)`` tuple.
    """
    if not text or not text.strip():
        return None, None

    has_explicit_date = _contains_explicit_date(text)
    has_explicit_time = _contains_explicit_time(text)

    parsed_date = _extract_date(text) if has_explicit_date else None
    parsed_time = _extract_time(text) if has_explicit_time else None

    if parsed_date is None and parsed_time is None:
        return None, None

    if parsed_date is not None:
        logger.info("event=date_parsed value=%s", parsed_date.isoformat())

    logger.info(
        "event=natural_date_parsed input=%r date=%s time=%s",
        text,
        parsed_date,
        parsed_time,
    )

    return parsed_date, parsed_time
