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

        self._tool_param_types = {
            "create_booking": {
                "customer_id": int,
                "service_type": str,
                "service_date": date,
                "service_time": time,
            },
            "reschedule_booking": {
                "booking_id": int,
                "new_date": date,
                "new_time": time,
            },
            "cancel_booking": {
                "booking_id": int,
            },
            "create_jobcard": {
                "booking_id": int,
                "technician_name": str | None,
            },
            "complete_jobcard": {
                "jobcard_id": int,
            },
            "get_daily_summary": {
                "target_date": date | None,
            },
        }
        self._openai_tool_definitions = self._build_openai_tool_definitions()

    def list_tools(self):
        return list(self._tools.keys())

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def get_openai_tool_definitions(self) -> list[dict]:
        return copy.deepcopy(self._openai_tool_definitions)

    def get_openai_tools(self) -> list[dict]:
        # Backward compatibility for older callers.
        return self.get_openai_tool_definitions()

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

    def execute(self, tool_name: str, db: Session, garage_id: int, **kwargs):
        if tool_name not in self._tools:
            raise ValueError(f"Tool '{tool_name}' not registered.")

        tool_function = self._tools[tool_name]
        function_parameters = inspect.signature(tool_function).parameters
        execute_kwargs = {"db": db}

        if "garage_id" in function_parameters:
            execute_kwargs["garage_id"] = garage_id

        for key, value in kwargs.items():
            if key in function_parameters and key != "db":
                execute_kwargs[key] = value
            else:
                logger.warning(
                    "Ignoring unsupported execute kwarg for '%s': %s",
                    tool_name,
                    key,
                )

        return tool_function(**execute_kwargs)

    def _build_openai_tool_definitions(self) -> list[dict]:
        tool_definitions = [
            {
                "type": "function",
                "function": {
                    "name": "create_booking",
                    "description": self._tool_descriptions["create_booking"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_id": {
                                "type": "integer",
                                "description": "Customer ID for booking.",
                            },
                            "service_type": {
                                "type": "string",
                                "description": "Type of requested service.",
                            },
                            "service_date": {
                                "type": "string",
                                "format": "date",
                                "description": "Service date in YYYY-MM-DD format.",
                            },
                            "service_time": {
                                "type": "string",
                                "description": "Service time in HH:MM format (24-hour).",
                            },
                        },
                        "required": [
                            "customer_id",
                            "service_type",
                            "service_date",
                            "service_time",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "reschedule_booking",
                    "description": self._tool_descriptions["reschedule_booking"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "booking_id": {
                                "type": "integer",
                                "description": "Booking ID to reschedule.",
                            },
                            "new_date": {
                                "type": "string",
                                "format": "date",
                                "description": "New service date in YYYY-MM-DD format.",
                            },
                            "new_time": {
                                "type": "string",
                                "description": "New service time in HH:MM format (24-hour).",
                            },
                        },
                        "required": ["booking_id", "new_date", "new_time"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "cancel_booking",
                    "description": self._tool_descriptions["cancel_booking"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "booking_id": {
                                "type": "integer",
                                "description": "Booking ID to cancel.",
                            },
                        },
                        "required": ["booking_id"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_jobcard",
                    "description": self._tool_descriptions["create_jobcard"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "booking_id": {
                                "type": "integer",
                                "description": "Booking ID to start work for.",
                            },
                            "technician_name": {
                                "type": "string",
                                "description": "Technician assigned to the job.",
                            },
                        },
                        "required": ["booking_id"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "complete_jobcard",
                    "description": self._tool_descriptions["complete_jobcard"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "jobcard_id": {
                                "type": "integer",
                                "description": "Job card ID to complete.",
                            },
                        },
                        "required": ["jobcard_id"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_daily_summary",
                    "description": self._tool_descriptions["get_daily_summary"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_date": {
                                "type": "string",
                                "format": "date",
                                "description": "Date in YYYY-MM-DD format. Defaults to today.",
                            },
                        },
                        "required": [],
                        "additionalProperties": False,
                    },
                },
            },
        ]

        logger.info(
            "ToolRegistry generated %d OpenAI tool definitions",
            len(tool_definitions),
        )
        return tool_definitions

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
