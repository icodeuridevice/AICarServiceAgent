"""Unit tests for the context extraction helper in llm_engine."""

import pytest

from garage_agent.ai.llm_engine import extract_fields_from_message


# ---------------------------------------------------------------------------
# Vehicle brand + model detection
# ---------------------------------------------------------------------------

class TestVehicleDetection:
    @pytest.mark.parametrize("brand", [
        "audi", "bmw", "mercedes", "toyota", "honda",
        "hyundai", "kia", "ford", "chevrolet", "nissan",
        "volkswagen", "mazda", "subaru", "lexus", "volvo",
    ])
    def test_detects_brand(self, brand):
        ctx = extract_fields_from_message(f"Book my {brand.title()} for service", {})
        assert ctx["vehicle"]["brand"] == brand

    def test_brand_case_insensitive(self):
        ctx = extract_fields_from_message("I have a BMW that needs repair", {})
        assert ctx["vehicle"]["brand"] == "bmw"

    def test_no_brand_does_not_set_vehicle(self):
        ctx = extract_fields_from_message("I need to book a service", {})
        assert "vehicle" not in ctx

    def test_brand_with_model(self):
        ctx = extract_fields_from_message("Book my Mercedes Maybach S680 for service", {})
        assert ctx["vehicle"]["brand"] == "mercedes"
        assert ctx["vehicle"]["model"] == "maybach s680"

    def test_brand_without_model(self):
        ctx = extract_fields_from_message("Book my BMW for service", {})
        assert ctx["vehicle"]["brand"] == "bmw"
        assert ctx["vehicle"]["model"] is None

    def test_brand_model_noise_stripped(self):
        ctx = extract_fields_from_message("Mercedes C Class needs repair", {})
        assert ctx["vehicle"]["brand"] == "mercedes"
        assert ctx["vehicle"]["model"] == "c class"


# ---------------------------------------------------------------------------
# Service type detection
# ---------------------------------------------------------------------------

class TestServiceTypeDetection:
    @pytest.mark.parametrize("keyword, expected", [
        ("routine", "routine"),
        ("maintenance", "maintenance"),
        ("oil", "oil_change"),
        ("inspection", "inspection"),
        ("repair", "repair"),
        ("service", "general_service"),
        ("brake", "brake_service"),
        ("tire", "tire_service"),
        ("battery", "battery_service"),
    ])
    def test_detects_service_type(self, keyword, expected):
        ctx = extract_fields_from_message(f"I need {keyword}", {})
        assert ctx["service_type"] == expected

    def test_no_service_keyword(self):
        ctx = extract_fields_from_message("Hello there", {})
        assert "service_type" not in ctx


# ---------------------------------------------------------------------------
# Date detection
# ---------------------------------------------------------------------------

class TestDateDetection:
    def test_iso_date(self):
        ctx = extract_fields_from_message("Date: 2026-03-17", {})
        assert ctx["service_date"] == "2026-03-17"

    def test_date_in_sentence(self):
        ctx = extract_fields_from_message("Can I book on 2026-04-01 please?", {})
        assert ctx["service_date"] == "2026-04-01"

    def test_no_date(self):
        ctx = extract_fields_from_message("Tomorrow maybe", {})
        assert "service_date" not in ctx


# ---------------------------------------------------------------------------
# Time detection
# ---------------------------------------------------------------------------

class TestTimeDetection:
    def test_hh_mm(self):
        ctx = extract_fields_from_message("Time: 15:35", {})
        assert ctx["service_time"] == "15:35"

    def test_time_in_sentence(self):
        ctx = extract_fields_from_message("at 09:00 would be great", {})
        assert ctx["service_time"] == "09:00"

    def test_no_time(self):
        ctx = extract_fields_from_message("Any time works", {})
        assert "service_time" not in ctx


# ---------------------------------------------------------------------------
# Combined / multi-field & context mutation
# ---------------------------------------------------------------------------

class TestCombinedExtraction:
    def test_full_message(self):
        ctx = extract_fields_from_message(
            "Book my Audi for routine on 2026-03-17 at 15:35", {}
        )
        assert ctx["vehicle"]["brand"] == "audi"
        assert ctx["service_type"] == "routine"
        assert ctx["service_date"] == "2026-03-17"
        assert ctx["service_time"] == "15:35"

    def test_incremental_context(self):
        ctx: dict = {}
        extract_fields_from_message("Book my BMW for service", ctx)
        assert ctx["vehicle"]["brand"] == "bmw"
        assert ctx["service_type"] == "general_service"

        extract_fields_from_message("Routine", ctx)
        assert ctx["service_type"] == "routine"
        assert ctx["vehicle"]["brand"] == "bmw"  # preserved

        extract_fields_from_message("Date: 2026-03-17 Time: 15:35", ctx)
        assert ctx["service_date"] == "2026-03-17"
        assert ctx["service_time"] == "15:35"
        # All four fields present
        assert set(ctx.keys()) >= {"vehicle", "service_type", "service_date", "service_time"}

    def test_overwrite_existing(self):
        ctx = {"vehicle": {"brand": "bmw", "model": None}, "service_type": "repair"}
        extract_fields_from_message("Actually, Audi for routine", ctx)
        assert ctx["vehicle"]["brand"] == "audi"
        assert ctx["service_type"] == "routine"

    def test_empty_message(self):
        ctx = {"vehicle": {"brand": "bmw", "model": None}}
        extract_fields_from_message("", ctx)
        assert ctx == {"vehicle": {"brand": "bmw", "model": None}}  # unchanged
