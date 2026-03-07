"""Persistent conversation memory for the AI assistant."""

import json
import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from garage_agent.db.models import AIConversation
from garage_agent.db.session import SessionLocal

logger = logging.getLogger(__name__)

_MAX_MESSAGES = 10


def _normalize_messages(messages_json: str | None) -> list[dict[str, str]]:
    if not messages_json:
        return []

    try:
        raw_messages = json.loads(messages_json)
    except json.JSONDecodeError:
        logger.warning("event=conversation_memory phase=invalid_json")
        return []

    if not isinstance(raw_messages, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            continue

        safe_role = role.strip()
        safe_content = content.strip()
        if not safe_role or not safe_content:
            continue

        normalized.append({"role": safe_role, "content": safe_content})

    return normalized[-_MAX_MESSAGES:]


def get_conversation(phone: str, garage_id: int) -> AIConversation | None:
    db = SessionLocal()
    try:
        return db.scalar(
            select(AIConversation)
            .where(AIConversation.phone == phone)
            .where(AIConversation.garage_id == garage_id)
            .order_by(AIConversation.id.desc())
        )
    finally:
        db.close()


def save_message(phone: str, garage_id: int, role: str, content: str) -> AIConversation | None:
    safe_role = (role or "").strip()
    safe_content = (content or "").strip()
    if not safe_role or not safe_content:
        return None

    db = SessionLocal()
    try:
        conversation = db.scalar(
            select(AIConversation)
            .where(AIConversation.phone == phone)
            .where(AIConversation.garage_id == garage_id)
            .order_by(AIConversation.id.desc())
        )
        if conversation is None:
            conversation = AIConversation(
                phone=phone,
                garage_id=garage_id,
                messages_json="[]",
            )
            db.add(conversation)
            db.flush()

        messages = _normalize_messages(conversation.messages_json)
        messages.append({"role": safe_role, "content": safe_content})
        conversation.messages_json = json.dumps(messages[-_MAX_MESSAGES:])

        db.commit()
        db.refresh(conversation)
        return conversation
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "event=conversation_memory phase=save_error phone=%s garage_id=%s",
            phone,
            garage_id,
        )
        raise
    finally:
        db.close()


def get_last_messages(phone: str, garage_id: int, limit: int = 10) -> list[dict[str, str]]:
    safe_limit = max(0, min(limit, _MAX_MESSAGES))
    if safe_limit == 0:
        return []

    conversation = get_conversation(phone=phone, garage_id=garage_id)
    if conversation is None:
        return []

    messages = _normalize_messages(conversation.messages_json)
    return messages[-safe_limit:]
