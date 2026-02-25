"""
LLM Engine – Agentic Execution Layer.

Responsible for:
1. Understanding user intent (LLM or rule fallback)
2. Deciding which tool to call
3. Returning structured tool intent
"""

import logging
from sqlalchemy.orm import Session

from garage_agent.ai.base_engine import BaseEngine
from garage_agent.ai.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class LLMEngine(BaseEngine):
    def __init__(self):
        self.registry = ToolRegistry()

    def process(self, db: Session, phone: str, message: str) -> dict:
        """
        Simulated LLM decision layer.
        Replace later with real OpenAI/Gemini structured tool calling.
        """

        logger.info("LLMEngine processing message: %s", message)

        message_lower = message.lower()

        # -------------------------
        # Tool decision logic (mock)
        # -------------------------
        if "summary" in message_lower:
            return {
                "engine": "llm",
                "type": "tool_call",
                "tool": "get_daily_summary",
                "reply": None,
                "result": None,
                "args": {},
            }

        # Example future trigger
        if "create job" in message_lower:
            return {
                "engine": "llm",
                "type": "tool_call",
                "tool": "create_jobcard",
                "reply": None,
                "result": None,
                "args": {
                    "booking_id": 1,
                    "technician_name": "Auto"
                },
            }

        # Default conversational fallback
        return {
            "engine": "llm",
            "type": "conversation",
            "reply": "Please provide more details so I can assist you.",
            "tool": None,
            "result": None,
        }

    def execute_tool(self, db: Session, tool_name: str, args: dict):
        """Executes tool via registry safely."""
        logger.info("Executing tool: %s with args: %s", tool_name, args)
        return self.registry.execute(
            tool_name=tool_name,
            db=db,
            **args,
        )
