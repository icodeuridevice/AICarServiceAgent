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
                tools=self.registry.get_openai_tools(),
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
            arguments = self.registry.sanitize_arguments(tool_name or "", parsed_arguments)

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
            response.setdefault("engine", "rule")
            response.setdefault("type", "conversation")
            response.setdefault("reply", "Request processed.")
            response.setdefault("tool", None)
            response.setdefault("arguments", None)
            response.setdefault("result", None)
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

        if not self.registry.has_tool(tool_name):
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

    def execute_tool(self, db: Session, tool_name: str, args: dict):
        """Executes tool via registry safely."""
        logger.info("Executing tool: %s with args: %s", tool_name, args)
        return self.registry.execute(
            tool_name=tool_name,
            db=db,
            **args,
        )
