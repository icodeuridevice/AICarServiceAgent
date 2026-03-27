"""Focused tests for the LLM booking confirmation flow."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import garage_agent.ai.llm_engine as llm_engine_module
from garage_agent.services import conversation_service


def _utc_today() -> date:
    return datetime.utcnow().date()


class StubProvider:
    def __init__(self, responses: list[str] | None = None):
        self.responses = list(responses or [])

    def generate(self, _messages):
        if not self.responses:
            raise AssertionError("Unexpected provider.generate call")
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def clear_conversation_state():
    conversation_service.conversation_store.clear()
    yield
    conversation_service.conversation_store.clear()


def _build_engine(monkeypatch, responses: list[str] | None = None):
    provider = StubProvider(responses)
    monkeypatch.setattr(llm_engine_module, "get_provider", lambda: provider)
    monkeypatch.setattr(llm_engine_module, "get_provider_name", lambda: "test")
    monkeypatch.setattr(
        llm_engine_module.ai_memory_service,
        "get_last_messages",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        llm_engine_module.ai_memory_service,
        "save_message",
        lambda *_args, **_kwargs: None,
    )
    engine = llm_engine_module.LLMEngine()
    return engine, provider


def _store_pending_confirmation(phone: str, *, service_date: str, service_time: str) -> None:
    conversation_service.update_data(
        phone,
        llm_engine_module._PENDING_ACTION_KEY,
        llm_engine_module._CONFIRM_BOOKING_ACTION,
    )
    conversation_service.update_data(
        phone,
        llm_engine_module._BOOKING_CONFIRMATION_KEY,
        {
            "tool_name": "create_booking",
            "arguments": {
                "customer_id": 7,
                "service_type": "routine",
                "service_date": service_date,
                "service_time": service_time,
            },
        },
    )


def test_create_booking_returns_confirmation_before_execution(monkeypatch):
    engine, _provider = _build_engine(monkeypatch, ['{"action":"create_booking"}'])
    monkeypatch.setattr(
        llm_engine_module,
        "get_or_create_customer_by_phone",
        lambda **_kwargs: SimpleNamespace(id=7),
    )
    engine.registry.execute = MagicMock()

    response = engine.process(
        db=MagicMock(),
        garage_id=1,
        phone="+10000000000",
        message="Book routine service tomorrow at 5pm",
    )

    expected_date = (_utc_today() + timedelta(days=1)).isoformat()
    assert response["type"] == "conversation"
    assert response["reply"] == (
        "Please confirm your booking:\n"
        "Service: Routine\n"
        f"Date: {expected_date}\n"
        "Time: 17:00\n\n"
        "Reply YES to confirm or NO to cancel."
    )
    assert engine.registry.execute.call_count == 0

    stored = conversation_service.get_data("+10000000000")
    pending = stored[llm_engine_module._BOOKING_CONFIRMATION_KEY]
    assert pending["arguments"]["service_date"] == expected_date
    assert pending["arguments"]["service_time"] == "17:00"
    assert stored[llm_engine_module._PENDING_ACTION_KEY] == llm_engine_module._CONFIRM_BOOKING_ACTION


def test_llm_confirmation_reply_is_replaced_by_backend_confirmation(monkeypatch):
    engine, _provider = _build_engine(
        monkeypatch,
        [
            '{"action":"conversation","reply":"Just to confirm, your routine service is for tomorrow at 5pm. Reply YES to confirm or NO to cancel."}'
        ],
    )
    monkeypatch.setattr(
        llm_engine_module,
        "get_or_create_customer_by_phone",
        lambda **_kwargs: SimpleNamespace(id=7),
    )
    engine.registry.execute = MagicMock()

    response = engine.process(
        db=MagicMock(),
        garage_id=1,
        phone="+10000000010",
        message="Book routine service tomorrow at 5pm",
    )

    expected_date = (_utc_today() + timedelta(days=1)).isoformat()
    assert response["type"] == "conversation"
    assert response["reply"] == (
        "Please confirm your booking:\n"
        "Service: Routine\n"
        f"Date: {expected_date}\n"
        "Time: 17:00\n\n"
        "Reply YES to confirm or NO to cancel."
    )
    assert engine.registry.execute.call_count == 0

    stored = conversation_service.get_data("+10000000010")
    assert stored[llm_engine_module._PENDING_ACTION_KEY] == llm_engine_module._CONFIRM_BOOKING_ACTION
    pending = stored[llm_engine_module._BOOKING_CONFIRMATION_KEY]
    assert pending["arguments"]["service_date"] == expected_date
    assert pending["arguments"]["service_time"] == "17:00"


def test_yes_executes_pending_booking(monkeypatch):
    engine, _provider = _build_engine(monkeypatch)
    engine.registry.execute = MagicMock(return_value={"success": True, "data": {"id": 42}})
    phone = "+10000000001"
    _store_pending_confirmation(phone, service_date="2026-03-30", service_time="17:00")

    response = engine.process(
        db=MagicMock(),
        garage_id=1,
        phone=phone,
        message="YES",
    )

    assert response["type"] == "tool_call"
    assert response["tool"] == "create_booking"
    assert response["reply"] == "Your booking is confirmed for Routine on 2026-03-30 at 17:00."
    assert conversation_service.get_data(phone) == {}
    engine.registry.execute.assert_called_once()


def test_no_cancels_pending_booking(monkeypatch):
    engine, _provider = _build_engine(monkeypatch)
    engine.registry.execute = MagicMock()
    phone = "+10000000002"
    _store_pending_confirmation(phone, service_date="2026-03-30", service_time="17:00")

    response = engine.process(
        db=MagicMock(),
        garage_id=1,
        phone=phone,
        message="NO",
    )

    assert response["type"] == "conversation"
    assert "cancelled this booking request" in response["reply"]
    assert conversation_service.get_data(phone) == {}
    assert engine.registry.execute.call_count == 0


def test_pending_confirmation_does_not_generate_duplicate_confirmation(monkeypatch):
    engine, _provider = _build_engine(monkeypatch)
    engine.registry.execute = MagicMock()
    phone = "+10000000020"
    _store_pending_confirmation(phone, service_date="2026-03-30", service_time="17:00")

    response = engine.process(
        db=MagicMock(),
        garage_id=1,
        phone=phone,
        message="Can you confirm again?",
    )

    assert response["type"] == "conversation"
    assert response["reply"] == "Please reply YES to confirm or NO to cancel."
    stored = conversation_service.get_data(phone)
    assert stored[llm_engine_module._PENDING_ACTION_KEY] == llm_engine_module._CONFIRM_BOOKING_ACTION
    assert llm_engine_module._BOOKING_CONFIRMATION_KEY in stored
    assert engine.registry.execute.call_count == 0


def test_booking_failure_prompts_for_corrected_field(monkeypatch):
    engine, _provider = _build_engine(monkeypatch)
    engine.registry.execute = MagicMock(
        return_value={
            "success": False,
            "data": None,
            "error": "Selected time slot is already booked.",
        }
    )
    phone = "+10000000003"
    _store_pending_confirmation(phone, service_date="2026-03-30", service_time="17:00")

    response = engine.process(
        db=MagicMock(),
        garage_id=1,
        phone=phone,
        message="YES",
    )

    assert response["type"] == "conversation"
    assert response["reply"] == (
        "I'm having trouble completing that right now. Let me help you step by step. "
        "Please share another preferred time."
    )

    stored = conversation_service.get_data(phone)
    assert stored["service_type"] == "routine"
    assert stored["service_date"] == "2026-03-30"
    assert "service_time" not in stored
    assert llm_engine_module._BOOKING_CONFIRMATION_KEY not in stored
