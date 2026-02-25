"""
LLM Engine – Agentic Execution Layer.

Responsible for:
1. Understanding user intent (LLM or rule fallback)
2. Deciding which tool to call
3. Executing selected tools via registry
4. Returning structured response payload
"""

import logging
import re
from sqlalchemy.orm import Session

from garage_agent.ai.base_engine import BaseEngine
from garage_agent.ai.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class LLMEngine(BaseEngine):
    def __init__(self):
        self.registry = ToolRegistry()

    def process(self, db: Session, phone: str, message: str) -> dict:
        """
        Deterministic intent mapping + tool execution.
        """

        safe_message = message or ""
        message_lower = safe_message.lower()

        logger.info("LLMEngine processing message from %s: %s", phone, safe_message)

        tool_name = self._select_tool_name(message_lower=message_lower)
        if tool_name is None:
            logger.info("LLMEngine selected conversation mode")
            return {
                "engine": "llm",
                "type": "conversation",
                "reply": "Please provide more details so I can assist you.",
                "tool": None,
                "arguments": None,
                "result": None,
            }

        arguments = self._build_arguments(tool_name=tool_name, message=safe_message)
        response = {
            "engine": "llm",
            "type": "tool_call",
            "reply": None,
            "tool": tool_name,
            "arguments": arguments,
            "result": None,
        }

        logger.info(
            "LLMEngine selected tool '%s' with arguments: %s",
            tool_name,
            arguments,
        )

        try:
            response["result"] = self.registry.execute(
                tool_name=tool_name,
                db=db,
                **arguments,
            )
            logger.info("LLMEngine tool '%s' executed successfully", tool_name)
        except Exception as exc:
            logger.exception("LLMEngine tool '%s' execution failed", tool_name)
            response["result"] = {
                "error": str(exc),
                "tool": tool_name,
                "arguments": arguments,
            }
            response["reply"] = "Tool execution failed."

        return response

    def _select_tool_name(self, message_lower: str) -> str | None:
        if "summary" in message_lower:
            return "get_daily_summary"
        if "cancel" in message_lower:
            return "cancel_booking"
        if "reschedule" in message_lower:
            return "reschedule_booking"
        if "complete job" in message_lower:
            return "complete_jobcard"
        return None

    def _build_arguments(self, tool_name: str, message: str) -> dict:
        arguments: dict = {}
        first_id = self._extract_first_int(message=message)

        if tool_name in {"cancel_booking", "reschedule_booking"} and first_id is not None:
            arguments["booking_id"] = first_id
        elif tool_name == "complete_jobcard" and first_id is not None:
            arguments["jobcard_id"] = first_id

        return arguments

    @staticmethod
    def _extract_first_int(message: str) -> int | None:
        match = re.search(r"\b\d+\b", message)
        if not match:
            return None
        return int(match.group(0))

    def execute_tool(self, db: Session, tool_name: str, args: dict):
        """Executes tool via registry safely."""
        logger.info("Executing tool: %s with args: %s", tool_name, args)
        return self.registry.execute(
            tool_name=tool_name,
            db=db,
            **args,
        )
