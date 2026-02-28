"""
LLM Engine – Agentic Execution Layer.

Responsible for:
1. Understanding user intent (LLM or rule fallback)
2. Requesting tool definitions from ToolRegistry
3. Executing selected tools via registry
4. Returning structured response payload
"""

import json
import logging
import os
from datetime import date, datetime, time
from typing import Any

from sqlalchemy.orm import Session

from garage_agent.ai.base_engine import BaseEngine
from garage_agent.ai.rule_engine import RuleEngine
from garage_agent.ai.tools.registry import ToolRegistry
from garage_agent.db.bootstrap import get_default_garage

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - import safety for environments without dependency
    OpenAI = None

logger = logging.getLogger(__name__)


class LLMEngine(BaseEngine):
    def __init__(self):
        self.registry = ToolRegistry()
        self.rule_engine = RuleEngine()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.system_prompt = (
            "You are a garage service assistant. "
            "When the request requires a backend action, call the best matching tool. "
            "When information is missing, ask a short clarifying question."
        )
        self.tool_result_prompt = (
            "A backend garage tool has already been executed successfully. "
            "Write a concise, customer-friendly WhatsApp reply using the tool result. "
            "Do not mention internal implementation details."
        )

        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if OpenAI and api_key else None

        if OpenAI is None:
            logger.error("openai package unavailable. Falling back to RuleEngine.")
        elif not api_key:
            logger.warning("OPENAI_API_KEY not set. Falling back to RuleEngine.")

    def process(self, db: Session, phone: str, message: str) -> dict:
        """
        OpenAI function-calling execution path.
        """

        safe_message = (message or "").strip()
        logger.info("LLMEngine processing message from %s", phone)

        if not safe_message:
            return self._conversation_response("Please provide more details so I can assist you.")

        if self.client is None:
            return self._fallback_to_rule(
                db=db,
                phone=phone,
                message=safe_message,
                reason="openai_client_unavailable",
            )

        try:
            garage_id = get_default_garage(db).id
            logger.info("Resolved garage_id=%s for LLM tool execution", garage_id)
        except Exception as exc:
            logger.exception("Failed to resolve default garage. Falling back to RuleEngine.")
            return self._fallback_to_rule(
                db=db,
                phone=phone,
                message=safe_message,
                reason="garage_resolution_error",
                error=exc,
            )

        try:
            logger.info("Calling OpenAI for initial tool-choice pass")
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                tool_choice="auto",
                tools=self.registry.get_openai_tool_definitions(),
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": safe_message},
                ],
            )
        except Exception as exc:
            logger.exception("OpenAI completion failed. Falling back to RuleEngine.")
            return self._fallback_to_rule(
                db=db,
                phone=phone,
                message=safe_message,
                reason="openai_api_error",
                error=exc,
            )

        try:
            message_obj = completion.choices[0].message
        except Exception as exc:
            logger.warning("OpenAI response malformed. Falling back to RuleEngine.")
            return self._fallback_to_rule(
                db=db,
                phone=phone,
                message=safe_message,
                reason="openai_malformed_response",
                error=exc,
            )

        tool_calls = getattr(message_obj, "tool_calls", None) or []
        if tool_calls:
            tool_call = tool_calls[0]
            tool_name = getattr(tool_call.function, "name", None)
            raw_arguments = getattr(tool_call.function, "arguments", "{}")
            logger.info(
                "OpenAI requested tool '%s' with raw arguments: %s",
                tool_name,
                raw_arguments,
            )

            if not tool_name:
                logger.warning("Tool call missing function name. Falling back to RuleEngine.")
                return self._fallback_to_rule(
                    db=db,
                    phone=phone,
                    message=safe_message,
                    reason="missing_tool_name",
                )

            if not self.registry.has_tool(tool_name):
                logger.warning("OpenAI requested unknown tool '%s'. Falling back to RuleEngine.", tool_name)
                return self._fallback_to_rule(
                    db=db,
                    phone=phone,
                    message=safe_message,
                    reason="unknown_tool",
                )

            try:
                parsed_arguments = self._parse_tool_arguments(raw_arguments)
            except ValueError as exc:
                logger.warning(
                    "Tool argument parse failed for '%s': %s. Falling back to RuleEngine.",
                    tool_name,
                    str(exc),
                )
                return self._fallback_to_rule(
                    db=db,
                    phone=phone,
                    message=safe_message,
                    reason="tool_argument_parse_error",
                    error=exc,
                )

            arguments = self.registry.sanitize_arguments(tool_name, parsed_arguments)

            logger.info(
                "Sanitized arguments for tool '%s': %s",
                tool_name,
                arguments,
            )

            try:
                tool_result = self.registry.execute(
                    tool_name=tool_name,
                    db=db,
                    garage_id=garage_id,
                    **arguments,
                )
                logger.info("Tool '%s' executed successfully", tool_name)
            except Exception as exc:
                logger.exception("Tool '%s' execution failed. Falling back to RuleEngine.", tool_name)
                return self._fallback_to_rule(
                    db=db,
                    phone=phone,
                    message=safe_message,
                    reason="tool_execution_error",
                    error=exc,
                )

            serialized_result = self._make_json_safe(tool_result)

            try:
                logger.info("Calling OpenAI for final customer-facing response synthesis")
                final_reply = self._generate_tool_followup_reply(
                    user_message=safe_message,
                    tool_name=tool_name,
                    tool_result=serialized_result,
                )
            except Exception as exc:
                logger.exception("OpenAI follow-up generation failed. Falling back to RuleEngine.")
                return self._fallback_to_rule(
                    db=db,
                    phone=phone,
                    message=safe_message,
                    reason="openai_followup_error",
                    error=exc,
                )

            return {
                "engine": "llm",
                "type": "tool_call",
                "tool": tool_name,
                "result": serialized_result,
                "reply": final_reply,
            }

        logger.info("No tool call requested by OpenAI; returning direct conversation response")
        reply = self._extract_message_text(message_obj) or "Request processed."
        return self._conversation_response(reply)

    def _fallback_to_rule(
        self,
        db: Session,
        phone: str,
        message: str,
        reason: str,
        error: Exception | None = None,
    ) -> dict:
        logger.warning(
            "LLMEngine fallback to RuleEngine triggered. reason=%s error=%s",
            reason,
            str(error) if error else None,
        )

        try:
            response = self.rule_engine.process(db=db, phone=phone, message=message)
        except Exception as exc:
            logger.exception("RuleEngine fallback failed")
            return {
                "engine": "rule",
                "type": "conversation",
                "reply": "Request processed.",
                "tool": None,
                "result": {"error": str(exc), "fallback_reason": reason},
            }

        if isinstance(response, dict):
            response.setdefault("engine", "rule")
            response.setdefault("type", "conversation")
            response.setdefault("reply", "Request processed.")
            response.setdefault("tool", None)
            response.setdefault("result", None)
            return response

        logger.warning("RuleEngine fallback returned non-dict: %r", response)
        return {
            "engine": "rule",
            "type": "conversation",
            "reply": "Request processed.",
            "tool": None,
            "result": {"error": "invalid_rule_engine_response", "fallback_reason": reason},
        }

    def _conversation_response(self, reply: str, result: Any = None) -> dict:
        return {
            "engine": "llm",
            "type": "conversation",
            "reply": reply,
            "tool": None,
            "result": result,
        }

    def _parse_tool_arguments(self, raw_arguments: Any) -> dict:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if raw_arguments is None:
            return {}
        if not isinstance(raw_arguments, str):
            raise ValueError(f"Tool arguments must be dict or JSON string, got {type(raw_arguments)!r}")

        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON tool arguments: {raw_arguments}") from exc

        if not isinstance(parsed, dict):
            raise ValueError(f"Tool arguments JSON is not an object: {parsed!r}")

        return parsed

    def execute_tool(self, db: Session, tool_name: str, args: dict, garage_id: int | None = None):
        """Executes tool via registry safely."""
        logger.info("Executing tool: %s with args: %s", tool_name, args)
        return self.registry.execute(
            tool_name=tool_name,
            db=db,
            garage_id=garage_id,
            **args,
        )

    def _generate_tool_followup_reply(
        self,
        user_message: str,
        tool_name: str,
        tool_result: Any,
    ) -> str:
        tool_result_payload = json.dumps(tool_result, ensure_ascii=False)
        completion = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": self.tool_result_prompt},
                {"role": "user", "content": user_message},
                {
                    "role": "user",
                    "content": (
                        f"Executed tool: {tool_name}\n"
                        f"Tool result JSON: {tool_result_payload}\n\n"
                        "Generate the final customer-facing response."
                    ),
                },
            ],
        )
        followup_message = completion.choices[0].message
        return self._extract_message_text(followup_message) or "Request processed."

    def _extract_message_text(self, message_obj: Any) -> str:
        content = getattr(message_obj, "content", None)
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text_value = item.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        parts.append(text_value.strip())
                else:
                    text_value = getattr(item, "text", None)
                    if isinstance(text_value, str) and text_value.strip():
                        parts.append(text_value.strip())
            return "\n".join(parts).strip()

        return ""

    def _make_json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, (date, datetime, time)):
            return value.isoformat()

        if isinstance(value, dict):
            return {
                str(key): self._make_json_safe(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [self._make_json_safe(item) for item in value]

        if hasattr(value, "__table__") and hasattr(value.__table__, "columns"):
            data: dict[str, Any] = {}
            for column in value.__table__.columns:
                data[column.name] = self._make_json_safe(getattr(value, column.name))
            return data

        return str(value)
