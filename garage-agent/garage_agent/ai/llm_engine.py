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
        self.tool_execution_failure_reply = "I couldn't complete that request. Please try again."

        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if OpenAI and api_key else None

        if OpenAI is None:
            logger.error("openai package unavailable. Falling back to RuleEngine.")
        elif not api_key:
            logger.warning("OPENAI_API_KEY not set. Falling back to RuleEngine.")

    def process(self, db: Session, garage_id: int, phone: str, message: str) -> dict:
        """
        OpenAI function-calling execution path.
        """

        safe_message = (message or "").strip()
        logger.info(
            "event=process_start engine=llm phone=%s garage_id=%s",
            phone,
            garage_id,
        )

        if not safe_message:
            return self._conversation_response("Please provide more details so I can assist you.")

        if self.client is None:
            return self._fallback_to_rule(
                db=db,
                garage_id=garage_id,
                phone=phone,
                message=safe_message,
                reason="openai_client_unavailable",
            )

        try:
            logger.info("event=model_call phase=start model=%s", self.model)
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
            logger.info("event=model_call phase=success model=%s", self.model)
        except Exception as exc:
            logger.exception("event=model_call phase=error model=%s", self.model)
            return self._fallback_to_rule(
                db=db,
                garage_id=garage_id,
                phone=phone,
                message=safe_message,
                reason="openai_api_error",
                error=exc,
            )

        try:
            message_obj = completion.choices[0].message
        except Exception as exc:
            logger.warning("event=model_call phase=malformed_response model=%s", self.model)
            return self._fallback_to_rule(
                db=db,
                garage_id=garage_id,
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

            if not tool_name:
                logger.warning("event=tool_decision decision=missing_tool_name")
                return self._fallback_to_rule(
                    db=db,
                    garage_id=garage_id,
                    phone=phone,
                    message=safe_message,
                    reason="missing_tool_name",
                )

            if not self.registry.has_tool(tool_name):
                logger.warning("event=tool_decision decision=unknown_tool tool=%s", tool_name)
                return self._fallback_to_rule(
                    db=db,
                    garage_id=garage_id,
                    phone=phone,
                    message=safe_message,
                    reason="unknown_tool",
                )

            try:
                parsed_arguments = self._parse_tool_arguments(raw_arguments)
            except ValueError as exc:
                logger.warning("event=tool_decision decision=argument_parse_error tool=%s", tool_name)
                return self._fallback_to_rule(
                    db=db,
                    garage_id=garage_id,
                    phone=phone,
                    message=safe_message,
                    reason="tool_argument_parse_error",
                    error=exc,
                )

            arguments = self.registry.sanitize_arguments(tool_name, parsed_arguments)
            logger.info(
                "event=tool_decision decision=tool_selected tool=%s argument_keys=%s",
                tool_name,
                sorted(arguments.keys()),
            )

            logger.info("event=tool_execution phase=start tool=%s", tool_name)
            try:
                tool_execution = self.registry.execute(
                    tool_name=tool_name,
                    db=db,
                    garage_id=garage_id,
                    **arguments,
                )
            except Exception:
                logger.exception("event=tool_execution phase=error tool=%s", tool_name)
                return self._tool_execution_failure_response()

            if not isinstance(tool_execution, dict):
                logger.warning(
                    "event=tool_execution phase=invalid_response tool=%s response_type=%s",
                    tool_name,
                    type(tool_execution).__name__,
                )
                return self._tool_execution_failure_response()

            execution_success = bool(tool_execution.get("success"))
            logger.info(
                "event=tool_execution phase=finish tool=%s success=%s",
                tool_name,
                execution_success,
            )
            if not execution_success:
                logger.warning(
                    "event=tool_execution phase=failed tool=%s error=%s",
                    tool_name,
                    tool_execution.get("error"),
                )
                return self._tool_execution_failure_response()

            serialized_result = self._make_json_safe(tool_execution.get("data"))

            try:
                logger.info("event=model_call phase=followup_start model=%s tool=%s", self.model, tool_name)
                final_reply = self._generate_tool_followup_reply(
                    user_message=safe_message,
                    tool_name=tool_name,
                    tool_result=serialized_result,
                )
                logger.info("event=model_call phase=followup_success model=%s tool=%s", self.model, tool_name)
            except Exception as exc:
                logger.exception("event=model_call phase=followup_error model=%s tool=%s", self.model, tool_name)
                return self._fallback_to_rule(
                    db=db,
                    garage_id=garage_id,
                    phone=phone,
                    message=safe_message,
                    reason="openai_followup_error",
                    error=exc,
                )

            return self._response_contract(
                engine="llm",
                response_type="tool_call",
                reply=final_reply,
                tool=tool_name,
                arguments=arguments,
                result=serialized_result,
            )

        logger.info("event=tool_decision decision=conversation")
        reply = self._extract_message_text(message_obj) or "Request processed."
        return self._conversation_response(reply)

    def _fallback_to_rule(
        self,
        db: Session,
        garage_id: int,
        phone: str,
        message: str,
        reason: str,
        error: Exception | None = None,
    ) -> dict:
        logger.warning(
            "event=fallback_trigger reason=%s error=%s",
            reason,
            str(error) if error else None,
        )

        try:
            response = self.rule_engine.process(
                db=db,
                garage_id=garage_id,
                phone=phone,
                message=message,
            )
        except Exception:
            logger.exception("event=fallback_trigger reason=%s phase=rule_engine_error", reason)
            return self._response_contract(
                engine="rule",
                response_type="conversation",
                reply=self.tool_execution_failure_reply,
                tool=None,
                arguments=None,
                result=None,
            )

        return self._normalize_rule_response(response)

    def _normalize_rule_response(self, response: Any) -> dict:
        if not isinstance(response, dict):
            logger.warning(
                "event=fallback_trigger phase=normalize invalid_rule_response_type=%s",
                type(response).__name__,
            )
            return self._response_contract(
                engine="rule",
                response_type="conversation",
                reply="Request processed.",
                tool=None,
                arguments=None,
                result=None,
            )

        return self._response_contract(
            engine="rule",
            response_type=response.get("type", "conversation"),
            reply=response.get("reply", "Request processed."),
            tool=response.get("tool"),
            arguments=response.get("arguments"),
            result=response.get("result"),
        )

    def _tool_execution_failure_response(self) -> dict:
        return self._response_contract(
            engine="llm",
            response_type="conversation",
            reply=self.tool_execution_failure_reply,
            tool=None,
            arguments=None,
            result=None,
        )

    def _conversation_response(self, reply: str, result: Any = None) -> dict:
        return self._response_contract(
            engine="llm",
            response_type="conversation",
            reply=reply,
            tool=None,
            arguments=None,
            result=result,
        )

    def _response_contract(
        self,
        engine: str,
        response_type: str,
        reply: Any,
        tool: Any,
        arguments: Any,
        result: Any,
    ) -> dict:
        normalized_type = response_type if response_type in {"conversation", "tool_call"} else "conversation"
        normalized_reply = reply.strip() if isinstance(reply, str) else ""
        if not normalized_reply:
            normalized_reply = "Request processed."

        normalized_tool = tool if isinstance(tool, str) and tool.strip() else None
        normalized_arguments = self._make_json_safe(arguments) if isinstance(arguments, dict) else None
        if normalized_arguments is not None and not isinstance(normalized_arguments, dict):
            normalized_arguments = None

        if normalized_type != "tool_call":
            normalized_tool = None
            normalized_arguments = None

        normalized_result = self._make_json_safe(result) if result is not None else None

        return {
            "engine": engine,
            "type": normalized_type,
            "reply": normalized_reply,
            "tool": normalized_tool,
            "arguments": normalized_arguments,
            "result": normalized_result,
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

    def execute_tool(self, db: Session, tool_name: str, args: dict, garage_id: int):
        """Executes tool via registry safely."""
        logger.info("event=tool_execution phase=external_execute tool=%s", tool_name)
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
