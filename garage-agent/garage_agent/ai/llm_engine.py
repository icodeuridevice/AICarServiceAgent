"""
LLM Engine – Agentic Execution Layer.

Responsible for:
1. Understanding user intent (LLM or rule fallback)
2. Converting registry tools to OpenAI function specs
3. Executing selected tools via registry
4. Returning structured response payload
"""

import inspect
import json
import logging
import os
import types
from datetime import date, datetime, time
from typing import Any, Union, get_args, get_origin

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

        self._tool_specs, self._tool_param_types = self._build_openai_tool_specs()
        self._tool_names = set(self.registry.list_tools())

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
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                tool_choice="auto",
                tools=self._tool_specs,
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

        tool_calls = message_obj.tool_calls or []
        if tool_calls:
            tool_call = tool_calls[0]
            tool_name = getattr(tool_call.function, "name", None)
            raw_arguments = getattr(tool_call.function, "arguments", "{}")
            parsed_arguments = self._parse_tool_arguments(raw_arguments)
            arguments = self._sanitize_and_coerce_arguments(tool_name, parsed_arguments)

            logger.info(
                "OpenAI requested tool '%s' with arguments: %s",
                tool_name,
                arguments,
            )

            return self._execute_tool_call(db=db, tool_name=tool_name, arguments=arguments)

        reply = (message_obj.content or "").strip() or "Request processed."
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
                "arguments": None,
                "result": {"error": str(exc), "fallback_reason": reason},
            }

        if isinstance(response, dict):
            return response

        logger.warning("RuleEngine fallback returned non-dict: %r", response)
        return {
            "engine": "rule",
            "type": "conversation",
            "reply": "Request processed.",
            "tool": None,
            "arguments": None,
            "result": {"error": "invalid_rule_engine_response", "fallback_reason": reason},
        }

    def _conversation_response(self, reply: str, result: Any = None) -> dict:
        return {
            "engine": "llm",
            "type": "conversation",
            "reply": reply,
            "tool": None,
            "arguments": None,
            "result": result,
        }

    def _execute_tool_call(self, db: Session, tool_name: str | None, arguments: dict) -> dict:
        response = {
            "engine": "llm",
            "type": "tool_call",
            "reply": None,
            "tool": tool_name,
            "arguments": arguments,
            "result": None,
        }

        if not tool_name:
            response["reply"] = "Tool execution failed."
            response["result"] = {"error": "missing_tool_name"}
            return response

        if tool_name not in self._tool_names:
            response["reply"] = "Tool execution failed."
            response["result"] = {
                "error": f"Tool '{tool_name}' not registered.",
                "tool": tool_name,
                "arguments": arguments,
            }
            return response

        try:
            response["result"] = self.registry.execute(
                tool_name=tool_name,
                db=db,
                **arguments,
            )
            logger.info("LLMEngine tool '%s' executed successfully", tool_name)
        except Exception as exc:
            logger.exception("LLMEngine tool '%s' execution failed", tool_name)
            response["reply"] = "Tool execution failed."
            response["result"] = {
                "error": str(exc),
                "tool": tool_name,
                "arguments": arguments,
            }

        return response

    def _build_openai_tool_specs(self) -> tuple[list[dict], dict[str, dict[str, Any]]]:
        tool_specs: list[dict] = []
        tool_param_types: dict[str, dict[str, Any]] = {}
        registry_tools = getattr(self.registry, "_tools", {})

        if not isinstance(registry_tools, dict):
            logger.error("ToolRegistry internal tool map is unavailable.")
            return tool_specs, tool_param_types

        for tool_name, tool_function in registry_tools.items():
            signature = inspect.signature(tool_function)
            doc = (inspect.getdoc(tool_function) or "").strip()
            description = doc.splitlines()[0] if doc else f"Execute `{tool_name}`."

            properties: dict[str, dict] = {}
            required: list[str] = []
            param_types: dict[str, Any] = {}

            for param_name, param in signature.parameters.items():
                if param_name == "db":
                    continue

                annotation = param.annotation
                param_types[param_name] = annotation
                properties[param_name] = self._annotation_to_schema(
                    param_name=param_name,
                    annotation=annotation,
                )

                if param.default is inspect._empty:
                    required.append(param_name)

            tool_specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": description,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                            "additionalProperties": False,
                        },
                    },
                }
            )
            tool_param_types[tool_name] = param_types

        logger.info("LLMEngine registered %d OpenAI tool specs", len(tool_specs))
        return tool_specs, tool_param_types

    def _annotation_to_schema(self, param_name: str, annotation: Any) -> dict:
        normalized_type, _ = self._normalize_annotation(annotation)

        schema_type = "string"
        if normalized_type is bool:
            schema_type = "boolean"
        elif normalized_type is int:
            schema_type = "integer"
        elif normalized_type is float:
            schema_type = "number"

        schema: dict[str, Any] = {
            "type": schema_type,
            "description": f"{param_name.replace('_', ' ')}",
        }

        if normalized_type is date:
            schema["type"] = "string"
            schema["format"] = "date"
            schema["description"] = "Date in YYYY-MM-DD format."
        elif normalized_type is time:
            schema["type"] = "string"
            schema["description"] = "Time in HH:MM format."
        elif normalized_type is datetime:
            schema["type"] = "string"
            schema["format"] = "date-time"

        return schema

    def _normalize_annotation(self, annotation: Any) -> tuple[Any, bool]:
        origin = get_origin(annotation)
        if origin in (Union, types.UnionType):
            args = get_args(annotation)
            non_none_args = [arg for arg in args if arg is not type(None)]
            nullable = len(non_none_args) != len(args)
            if len(non_none_args) == 1:
                return non_none_args[0], nullable
            return str, nullable

        if annotation in (inspect._empty, Any):
            return str, False

        return annotation, False

    def _parse_tool_arguments(self, raw_arguments: Any) -> dict:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not isinstance(raw_arguments, str):
            logger.warning("Tool arguments were not a dict/string: %r", raw_arguments)
            return {}

        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON tool arguments: %s", raw_arguments)
            return {}

        if not isinstance(parsed, dict):
            logger.warning("Tool arguments JSON is not an object: %r", parsed)
            return {}

        return parsed

    def _sanitize_and_coerce_arguments(self, tool_name: str | None, arguments: dict) -> dict:
        if not tool_name:
            return {}

        expected_params = self._tool_param_types.get(tool_name, {})
        sanitized: dict[str, Any] = {}

        for key, value in arguments.items():
            if key not in expected_params:
                continue
            sanitized[key] = self._coerce_value(value=value, annotation=expected_params[key])

        dropped_keys = set(arguments.keys()) - set(sanitized.keys())
        if dropped_keys:
            logger.warning("Dropped unsupported arguments for '%s': %s", tool_name, dropped_keys)

        return sanitized

    def _coerce_value(self, value: Any, annotation: Any) -> Any:
        target_type, _ = self._normalize_annotation(annotation)
        if value is None:
            return None

        try:
            if target_type is bool:
                if isinstance(value, str):
                    lowered = value.strip().lower()
                    if lowered in {"true", "yes", "1"}:
                        return True
                    if lowered in {"false", "no", "0"}:
                        return False
                return bool(value)

            if target_type is int and not isinstance(value, int):
                return int(value)

            if target_type is float and not isinstance(value, float):
                return float(value)

            if target_type is str and not isinstance(value, str):
                return str(value)

            if target_type is date and isinstance(value, str):
                return date.fromisoformat(value)

            if target_type is time and isinstance(value, str):
                return time.fromisoformat(value)

            if target_type is datetime and isinstance(value, str):
                return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            logger.warning("Failed to coerce value '%s' to %s", value, target_type)

        return value

    def execute_tool(self, db: Session, tool_name: str, args: dict):
        """Executes tool via registry safely."""
        logger.info("Executing tool: %s with args: %s", tool_name, args)
        return self.registry.execute(
            tool_name=tool_name,
            db=db,
            **args,
        )
