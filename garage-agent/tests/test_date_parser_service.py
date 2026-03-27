"""Unit tests for the natural language date/time parser service."""

from datetime import date, timedelta, time

import pytest

from garage_agent.services.date_parser_service import parse_natural_datetime


class TestParseNaturalDatetime:
    """Core parsing tests."""

    def test_tomorrow_returns_date_no_time(self):
        parsed_date, parsed_time = parse_natural_datetime("tomorrow")
        expected = date.today() + timedelta(days=1)
        assert parsed_date == expected
        assert parsed_time is None  # no explicit time → should ask user

    def test_today_4pm(self):
        parsed_date, parsed_time = parse_natural_datetime("today 4pm")
        assert parsed_date == date.today()
        assert parsed_time == time(16, 0)

    def test_next_monday_10am(self):
        parsed_date, parsed_time = parse_natural_datetime("next monday 10am")
        assert parsed_date is not None
        assert parsed_date > date.today()
        assert parsed_date.weekday() == 0  # Monday
        assert parsed_time == time(10, 0)

    def test_day_after_tomorrow_evening(self):
        parsed_date, parsed_time = parse_natural_datetime("day after tomorrow evening")
        expected_date = date.today() + timedelta(days=2)
        assert parsed_date == expected_date
        assert parsed_time == time(18, 0)

    def test_5pm_returns_time_only(self):
        parsed_date, parsed_time = parse_natural_datetime("5pm")
        assert parsed_date is None
        assert parsed_time == time(17, 0)

    def test_evening_returns_time_only(self):
        parsed_date, parsed_time = parse_natural_datetime("evening")
        assert parsed_date is None
        assert parsed_time == time(18, 0)

    def test_gibberish_returns_none(self):
        parsed_date, parsed_time = parse_natural_datetime("asdf jkl random gibberish")
        assert parsed_date is None
        assert parsed_time is None

    def test_empty_string(self):
        parsed_date, parsed_time = parse_natural_datetime("")
        assert parsed_date is None
        assert parsed_time is None

    def test_none_like_whitespace(self):
        parsed_date, parsed_time = parse_natural_datetime("   ")
        assert parsed_date is None
        assert parsed_time is None

    def test_iso_date_still_parsed(self):
        """Explicit ISO dates should still be resolved by dateparser."""
        parsed_date, parsed_time = parse_natural_datetime("2026-04-01")
        assert parsed_date == date(2026, 4, 1)

    def test_morning_indicator(self):
        parsed_date, parsed_time = parse_natural_datetime("tomorrow morning")
        expected = date.today() + timedelta(days=1)
        assert parsed_date == expected
        assert parsed_time is not None

    def test_noon(self):
        parsed_date, parsed_time = parse_natural_datetime("tomorrow noon")
        expected = date.today() + timedelta(days=1)
        assert parsed_date == expected
        assert parsed_time is not None
