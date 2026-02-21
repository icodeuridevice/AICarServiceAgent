"""In-memory conversation state and metadata for multi-step booking chats."""

from typing import Any

# Per-user conversation state:
# {
#   phone: {
#       "state": str,
#       "data": dict,
#   }
# }
conversation_store: dict[str, dict[str, Any]] = {}


def get_state(phone: str) -> str | None:
    """Return the current conversation state for a phone number."""
    conversation = conversation_store.get(phone)
    if not conversation:
        return None
    state = conversation.get("state")
    return state if isinstance(state, str) else None


def set_state(phone: str, state: str) -> None:
    """Set conversation state while preserving existing stored data."""
    conversation = conversation_store.setdefault(phone, {"state": state, "data": {}})
    conversation["state"] = state
    conversation.setdefault("data", {})


def update_data(phone: str, key: str, value: Any) -> None:
    """Store a key/value pair inside the phone-specific conversation data."""
    conversation = conversation_store.setdefault(phone, {"state": None, "data": {}})
    data = conversation.setdefault("data", {})
    if not isinstance(data, dict):
        data = {}
        conversation["data"] = data
    data[key] = value


def get_data(phone: str) -> dict[str, Any]:
    """Return conversation data dictionary for a phone number."""
    conversation = conversation_store.get(phone)
    if not conversation:
        return {}
    data = conversation.get("data")
    return data if isinstance(data, dict) else {}


def clear_state(phone: str) -> None:
    """Remove all state and cached data for a phone number."""
    conversation_store.pop(phone, None)
