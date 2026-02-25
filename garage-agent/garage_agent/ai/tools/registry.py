"""
Central AI Tool Registry.

Maps tool names to executable functions.
This allows LLM engine to dynamically call tools.
"""

import copy
import inspect
import logging
import types
from datetime import date, datetime, time
from typing import Any, Union, get_args, get_origin

from sqlalchemy.orm import Session

from garage_agent.ai.tools.booking_tools import (
    tool_create_booking,
    tool_reschedule_booking,
    tool_cancel_booking,
)

from garage_agent.ai.tools.jobcard_tools import (
    tool_create_jobcard,
    tool_complete_jobcard,
)

from garage_agent.ai.tools.report_tools import (
    tool_get_daily_summary,
)

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self):
        self._tools = {
            # Booking tools
            "create_booking": tool_create_booking,
            "reschedule_booking": tool_reschedule_booking,
            "cancel_booking": tool_cancel_booking,

            # JobCard tools
            "create_jobcard": tool_create_jobcard,
            "complete_jobcard": tool_complete_jobcard,

            # Reporting tools
            "get_daily_summary": tool_get_daily_summary,
        }

        self._tool_descriptions = {
            "create_booking": "Create a new service booking for a customer.",
            "reschedule_booking": "Reschedule an existing booking to a new date and time.",
            "cancel_booking": "Cancel an existing booking by booking ID.",
            "create_jobcard": "Create a job card for a booking.",
            "complete_jobcard": "Mark a job card as completed.",
            "get_daily_summary": "Get daily bookings and revenue summary.",
        }

        self._openai_tools, self._tool_param_types = self._build_openai_tools()

    def list_tools(self):
        return list(self._tools.keys())

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def get_openai_tools(self) -> list[dict]:
        return copy.deepcopy(self._openai_tools)

    def sanitize_arguments(self, tool_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        if not tool_name or not isinstance(arguments, dict):
            return {}

        expected_params = self._tool_param_types.get(tool_name, {})
        sanitized: dict[str, Any] = {}

        for key, value in arguments.items():
            if key not in expected_params:
                continue
            sanitized[key] = self._coerce_value(value=value, annotation=expected_params[key])

        dropped_keys = set(arguments.keys()) - set(sanitized.keys())
        if dropped_keys:
            logger.warning(
                "Dropped unsupported arguments for '%s': %s",
                tool_name,
                sorted(dropped_keys),
            )

        return sanitized

    def execute(self, tool_name: str, db: Session, **kwargs):
        if tool_name not in self._tools:
            raise ValueError(f"Tool '{tool_name}' not registered.")

        tool_function = self._tools[tool_name]
        return tool_function(db=db, **kwargs)

    def _build_openai_tools(self) -> tuple[list[dict], dict[str, dict[str, Any]]]:
        openai_tools: list[dict] = []
        tool_param_types: dict[str, dict[str, Any]] = {}

        for tool_name, tool_function in self._tools.items():
            signature = inspect.signature(tool_function)
            description = self._get_tool_description(tool_name, tool_function)

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

            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": description,
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                        },
                    },
                }
            )
            tool_param_types[tool_name] = param_types

        logger.info("ToolRegistry generated %d OpenAI tool definitions", len(openai_tools))
        return openai_tools, tool_param_types

    def _get_tool_description(self, tool_name: str, tool_function: Any) -> str:
        configured = self._tool_descriptions.get(tool_name)
        if configured:
            return configured

        doc = (inspect.getdoc(tool_function) or "").strip()
        if doc:
            return doc.splitlines()[0]

        return f"Execute tool '{tool_name}'."

    def _annotation_to_schema(self, param_name: str, annotation: Any) -> dict:
        normalized_type = self._normalize_annotation(annotation)

        schema_type = "string"
        if normalized_type is bool:
            schema_type = "boolean"
        elif normalized_type is int:
            schema_type = "integer"
        elif normalized_type is float:
            schema_type = "number"

        schema: dict[str, Any] = {
            "type": schema_type,
            "description": param_name.replace("_", " "),
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

    def _normalize_annotation(self, annotation: Any) -> Any:
        origin = get_origin(annotation)
        if origin in (Union, types.UnionType):
            args = get_args(annotation)
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                return non_none_args[0]
            return str

        if annotation in (inspect._empty, Any):
            return str

        return annotation

    def _coerce_value(self, value: Any, annotation: Any) -> Any:
        target_type = self._normalize_annotation(annotation)
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
