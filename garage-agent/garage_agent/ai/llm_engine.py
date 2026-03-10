"""
LLM Engine – Agentic Execution Layer (Ollama / qwen3.5:0.8b).

Responsible for:
1. Understanding user intent (LLM or rule fallback)
2. Requesting tool definitions from ToolRegistry
3. Executing selected tools via registry
4. Returning structured response payload

Provider: local Ollama instance (HTTP POST to /api/chat).
"""

import json
import logging
import os
import time as _time
from datetime import date, datetime, time
from typing import Any

import requests
from sqlalchemy.orm import Session

from garage_agent.ai.base_engine import BaseEngine
from garage_agent.ai.rule_engine import RuleEngine
from garage_agent.ai.tools.registry import ToolRegistry
from garage_agent.services import ai_memory_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an AI assistant for a car service garage.

Your job is to help customers with vehicle service requests such as:
- booking service appointments
- answering service questions
- checking booking status
- assisting with vehicle issues

IMPORTANT RULES:

1. Never mention internal tools.
2. Never ask the user which tool to use.
3. Tools such as booking systems or job cards are internal mechanisms.
4. Always speak naturally like a human customer service assistant.

When a user reports a vehicle problem:
- express empathy
- offer to schedule a service appointment

When a booking is requested:
collect missing information step by step.

Required booking information:
- vehicle
- service type
- preferred date
- preferred time

If any information is missing, ask the user politely for that information.

Only confirm a booking once all required information is collected.

Never expose system architecture, APIs, or internal tool names.

Keep responses short, friendly, and helpful.
"""

_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
_DEFAULT_OLLAMA_MODEL = "qwen3.5:0.8b"
_DEFAULT_OLLAMA_NUM_PREDICT = 120
_DEFAULT_OLLAMA_FOLLOWUP_NUM_PREDICT = 200  # higher limit for follow-up replies
_DEFAULT_OLLAMA_TIMEOUT = 300          # seconds – generous for CPU inference
_DEFAULT_OLLAMA_KEEP_ALIVE = "30m"     # keep model resident in RAM
_DEFAULT_OLLAMA_RETRIES = 2            # retry count for transient Ollama failures
_DEFAULT_MEMORY_MESSAGE_LIMIT = 10


class LLMEngine(BaseEngine):
    def __init__(self):
        self.registry = ToolRegistry()
        self.rule_engine = RuleEngine()

        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", _DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL)

        self.system_prompt = SYSTEM_PROMPT
        self.max_memory_messages = _DEFAULT_MEMORY_MESSAGE_LIMIT
        self.tool_result_prompt = (
            "A backend garage tool has already been executed successfully. "
            "Write a concise, customer-friendly WhatsApp reply using the tool result. "
            "Do not mention internal implementation details."
        )
        self.tool_execution_failure_reply = "I couldn't complete that request. Please try again."

        logger.info(
            "event=llm_engine_init model=%s base_url=%s",
            self.model,
            self.ollama_base_url,
        )

    # ------------------------------------------------------------------
    # Ollama HTTP transport
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        user_message: str,
        history: list[dict[str, str]] | None = None,
        system_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": system_prompt or self.system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def _call_ollama(
        self,
        messages: list[dict[str, str]],
        num_predict: int = _DEFAULT_OLLAMA_NUM_PREDICT,
    ) -> str:
        """
        Send chat messages to the local Ollama instance and return the
        generated assistant text. Uses ``/api/chat`` with streaming
        disabled and temperature fixed at 0 for deterministic output.

        Performance knobs (CPU-friendly):
        * ``keep_alive`` – keeps the model loaded in RAM between calls.
        * ``timeout``    – 300 s to tolerate slow CPU inference.
        * ``num_predict`` – configurable max tokens per call.
        * Automatic retry with exponential backoff for transient failures.
        * Latency is measured and logged on every call.
        """
        url = f"{self.ollama_base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": num_predict,
            },
            "think": False,
            "keep_alive": _DEFAULT_OLLAMA_KEEP_ALIVE
        }
        logger.info("event=ollama_call phase=start url=%s model=%s", url, self.model)

        last_error: Exception | None = None
        for attempt in range(1, _DEFAULT_OLLAMA_RETRIES + 1):
            try:
                start = _time.time()
                response = requests.post(url, json=payload, timeout=_DEFAULT_OLLAMA_TIMEOUT)
                duration = _time.time() - start

                response.raise_for_status()
                data = response.json()
                generated_text = data.get("message", {}).get("content", "").strip()
                logger.info(
                    "event=ollama_call phase=success model=%s message_count=%d response_length=%d latency=%.2fs attempt=%d",
                    self.model,
                    len(messages),
                    len(generated_text),
                    duration,
                    attempt,
                )
                return generated_text
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "event=ollama_call phase=retry model=%s attempt=%d/%d error=%s",
                    self.model,
                    attempt,
                    _DEFAULT_OLLAMA_RETRIES,
                    str(exc),
                )
                if attempt < _DEFAULT_OLLAMA_RETRIES:
                    _time.sleep(min(2 ** attempt, 4))  # exponential backoff, max 4s

        # All retries exhausted — raise the last error
        raise last_error  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_tool_selection_system_prompt(self) -> str:
        """Build a strict planner prompt for the initial tool-selection call."""
        tool_descriptions = self._get_tool_description_block()

        return (
            f"{self.system_prompt}\n\n"
            "You are now deciding whether to continue the conversation directly "
            "or call one backend garage tool. Use the prior conversation history "
            "and the latest user message for context.\n\n"
            f"### AVAILABLE TOOLS\n{tool_descriptions}\n\n"
            "### OUTPUT FORMAT\n"
            "Respond ONLY with a single valid JSON object.\n"
            "Tool call format:\n"
            "{\"action\": \"<tool_name>\", \"arg1\": \"...\"}\n"
            "Conversation format:\n"
            "{\"action\": \"conversation\", \"reply\": \"<your reply>\"}\n\n"
            "Rules:\n"
            "1. Respond ONLY with a single valid JSON object and no extra text.\n"
            "2. Use the exact tool names listed above.\n"
            "3. Dates must be in YYYY-MM-DD format and times in HH:MM (24-hour).\n"
            "4. If required information is missing, use the conversation action "
            "to ask a clarifying question.\n\n"
            "Return the JSON response now."
        )

    def _get_tool_description_block(self) -> str:
        """
        Return a compact list of available tool names.

        Minimised to reduce token count for CPU-constrained inference;
        the model only needs to know *which* tools exist — the backend
        handles argument validation via ToolRegistry.
        """
        tool_names = self.registry.list_tools()
        if not tool_names:
            return "No tools available."
        # Plain newline-separated list — cheapest possible representation
        return "\n".join(f"- {name}" for name in tool_names)

    def _build_followup_prompt(
        self,
        user_message: str,
        tool_name: str,
        tool_result: Any,
    ) -> str:
        """
        Build a prompt that asks the LLM to compose a customer-friendly
        WhatsApp reply from a tool execution result.
        """
        tool_result_payload = json.dumps(tool_result, ensure_ascii=False)
        prompt = (
            f"### ADDITIONAL INSTRUCTIONS\n{self.tool_result_prompt}\n\n"
            f"### ORIGINAL USER MESSAGE\n{user_message}\n\n"
            f"### EXECUTED TOOL\n{tool_name}\n\n"
            f"### TOOL RESULT (JSON)\n{tool_result_payload}\n\n"
            "### INSTRUCTIONS\n"
            "Generate a concise, customer-friendly WhatsApp reply based on "
            "the tool result above. Do NOT output JSON — just the plain-text reply.\n"
        )
        return prompt

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process(self, db: Session, garage_id: int, phone: str, message: str) -> dict:
        """
        Ollama-based execution path.
        """
        safe_message = (message or "").strip()
        logger.info(
            "event=process_start engine=llm phone=%s garage_id=%s",
            phone,
            garage_id,
        )

        if not safe_message:
            return self._conversation_response("Please provide more details so I can assist you.")

        # ----- Step 1: Ask model to decide intent / tool -----
        history = self._load_conversation_history(phone=phone, garage_id=garage_id)
        tool_selection_messages = self._build_messages(
            user_message=safe_message,
            history=history,
            system_prompt=self._build_tool_selection_system_prompt(),
        )
        try:
            logger.info("event=model_call phase=start model=%s", self.model)
            raw_response = self._call_ollama(tool_selection_messages)
            logger.info("event=model_call phase=success model=%s", self.model)
        except Exception as exc:
            logger.exception("event=model_call phase=error model=%s", self.model)
            return self._fallback_to_rule(
                db=db,
                garage_id=garage_id,
                phone=phone,
                message=safe_message,
                reason="ollama_api_error",
                error=exc,
            )

        # ----- Step 2: Parse the JSON response -----
        try:
            parsed = self._extract_json(raw_response)
        except ValueError:
            # Smaller models (e.g. qwen3.5:0.8b) may return plain
            # conversational text instead of JSON.  Use the raw LLM
            # reply directly rather than discarding it.
            clean_reply = raw_response.strip()
            if clean_reply:
                logger.info(
                    "event=model_call phase=json_fallback_to_plain_text response_length=%d",
                    len(clean_reply),
                )
                return self._finalize_response(
                    response=self._conversation_response(clean_reply),
                    phone=phone,
                    garage_id=garage_id,
                    user_message=safe_message,
                )
            # Truly empty response — fall back to rule engine
            logger.warning("event=model_call phase=json_parse_error raw_response=<empty>")
            return self._fallback_to_rule(
                db=db,
                garage_id=garage_id,
                phone=phone,
                message=safe_message,
                reason="ollama_json_parse_empty",
            )

        action = parsed.get("action", "conversation")

        # ----- Step 3a: Conversational reply (no tool) -----
        if action == "conversation":
            reply = parsed.get("reply", "Request processed.")
            logger.info("event=tool_decision decision=conversation")
            return self._finalize_response(
                response=self._conversation_response(reply),
                phone=phone,
                garage_id=garage_id,
                user_message=safe_message,
            )

        # ----- Step 3b: Tool call -----
        tool_name = action

        if not self.registry.has_tool(tool_name):
            logger.warning("event=tool_decision decision=unknown_tool tool=%s", tool_name)
            return self._fallback_to_rule(
                db=db,
                garage_id=garage_id,
                phone=phone,
                message=safe_message,
                reason="unknown_tool",
            )

        # Extract arguments (everything except "action")
        raw_arguments = {k: v for k, v in parsed.items() if k != "action"}

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

        # ----- Step 4: Execute the tool -----
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
            return self._finalize_response(
                response=self._tool_execution_failure_response(),
                phone=phone,
                garage_id=garage_id,
                user_message=safe_message,
            )

        if not isinstance(tool_execution, dict):
            logger.warning(
                "event=tool_execution phase=invalid_response tool=%s response_type=%s",
                tool_name,
                type(tool_execution).__name__,
            )
            return self._finalize_response(
                response=self._tool_execution_failure_response(),
                phone=phone,
                garage_id=garage_id,
                user_message=safe_message,
            )

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
            return self._finalize_response(
                response=self._tool_execution_failure_response(),
                phone=phone,
                garage_id=garage_id,
                user_message=safe_message,
            )

        serialized_result = self._make_json_safe(tool_execution.get("data"))

        # ----- Vehicle health special handling -----
        if tool_name == "analyze_vehicle_health":
            result = serialized_result if isinstance(serialized_result, dict) else {}
            health_score = result.get(
                "health_score",
                result.get("vehicle_health_score", 100),
            )
            predicted_date = result.get("predicted_next_service_date")
            recurring_issues = result.get("recurring_issues", [])
            critical_flag = False

            if health_score < 40 or len(recurring_issues) >= 3:
                critical_flag = True

            escalation_message = None
            if critical_flag:
                logger.warning(
                    "CRITICAL VEHICLE CONDITION DETECTED | phone=%s | score=%s | recurring=%s",
                    phone,
                    health_score,
                    len(recurring_issues),
                )

                vehicle_id = arguments.get("vehicle_id")
                if vehicle_id is not None:
                    try:
                        from garage_agent.services.escalation_service import create_escalation

                        create_escalation(
                            db=db,
                            garage_id=garage_id,
                            vehicle_id=vehicle_id,
                            reason="Critical health score or repeated issue",
                            health_score=health_score,
                        )
                    except Exception:
                        logger.exception(
                            "event=escalation phase=error phone=%s garage_id=%s vehicle_id=%s",
                            phone,
                            garage_id,
                            vehicle_id,
                        )
                else:
                    logger.warning(
                        "event=escalation phase=skipped reason=missing_vehicle_id phone=%s",
                        phone,
                    )

                escalation_message = "⚠️ Critical vehicle condition detected. Staff review required."

            if health_score >= 80:
                urgency = "Low"
                recommendation = "Vehicle condition is good."
            elif health_score >= 50:
                urgency = "Medium"
                recommendation = "Service recommended soon."
            else:
                urgency = "High"
                recommendation = "Immediate inspection advised."

            health_reply = (
                f"Vehicle Health Score: {health_score}/100\n"
                f"Urgency Level: {urgency}\n"
                f"Predicted Next Service: {predicted_date}\n"
                f"Recurring Issues: {len(recurring_issues)} detected\n\n"
                f"Recommendation: {recommendation}"
            )

            return self._finalize_response(
                response={
                    "engine": "llm",
                    "type": "intelligence_report",
                    "reply": health_reply,
                    "tool": tool_name,
                    "result": result,
                    "critical": critical_flag,
                    "escalation_note": escalation_message,
                },
                phone=phone,
                garage_id=garage_id,
                user_message=safe_message,
            )

        # ----- Step 5: Generate follow-up reply via Ollama -----
        try:
            logger.info("event=model_call phase=followup_start model=%s tool=%s", self.model, tool_name)
            final_reply = self._generate_tool_followup_reply(
                user_message=safe_message,
                tool_name=tool_name,
                tool_result=serialized_result,
                history=history,
            )
            logger.info("event=model_call phase=followup_success model=%s tool=%s", self.model, tool_name)
        except Exception as exc:
            logger.exception("event=model_call phase=followup_error model=%s tool=%s", self.model, tool_name)
            return self._fallback_to_rule(
                db=db,
                garage_id=garage_id,
                phone=phone,
                message=safe_message,
                reason="ollama_followup_error",
                error=exc,
            )

        return self._finalize_response(
            response=self._response_contract(
                engine="llm",
                response_type="tool_call",
                reply=final_reply,
                tool=tool_name,
                arguments=arguments,
                result=serialized_result,
            ),
            phone=phone,
            garage_id=garage_id,
            user_message=safe_message,
        )

    # ------------------------------------------------------------------
    # Follow-up reply generation
    # ------------------------------------------------------------------

    def _generate_tool_followup_reply(
        self,
        user_message: str,
        tool_name: str,
        tool_result: Any,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        prompt = self._build_followup_prompt(user_message, tool_name, tool_result)
        reply = self._call_ollama(
            self._build_messages(prompt, history=history),
            num_predict=_DEFAULT_OLLAMA_FOLLOWUP_NUM_PREDICT,
        )
        return reply or "Request processed."

    def _load_conversation_history(self, phone: str, garage_id: int) -> list[dict[str, str]]:
        try:
            history = ai_memory_service.get_last_messages(
                phone=phone,
                garage_id=garage_id,
                limit=self.max_memory_messages,
            )
        except Exception:
            logger.exception(
                "event=conversation_memory phase=load_error phone=%s garage_id=%s",
                phone,
                garage_id,
            )
            return []

        logger.info(
            "event=conversation_memory phase=load phone=%s garage_id=%s message_count=%d",
            phone,
            garage_id,
            len(history),
        )
        return history

    def _persist_conversation_turn(
        self,
        phone: str,
        garage_id: int,
        user_message: str,
        assistant_reply: str,
    ) -> None:
        safe_user_message = user_message.strip()
        safe_assistant_reply = assistant_reply.strip()
        if not safe_user_message or not safe_assistant_reply:
            return

        try:
            ai_memory_service.save_message(phone, garage_id, "user", safe_user_message)
            ai_memory_service.save_message(phone, garage_id, "assistant", safe_assistant_reply)
        except Exception:
            logger.exception(
                "event=conversation_memory phase=save_error phone=%s garage_id=%s",
                phone,
                garage_id,
            )
            return

        logger.info(
            "event=conversation_memory phase=save phone=%s garage_id=%s",
            phone,
            garage_id,
        )

    def _finalize_response(
        self,
        response: dict,
        phone: str,
        garage_id: int,
        user_message: str,
    ) -> dict:
        reply = response.get("reply")
        if isinstance(reply, str):
            self._persist_conversation_turn(
                phone=phone,
                garage_id=garage_id,
                user_message=user_message,
                assistant_reply=reply,
            )
        return response

    # ------------------------------------------------------------------
    # JSON extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> dict:
        """
        Attempt to parse JSON from LLM output.  Handles the common case
        where the model wraps JSON in markdown fences (```json ... ```).
        """
        cleaned = text.strip()

        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
            cleaned = cleaned[first_newline + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        # Try to find JSON object boundaries
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_str = cleaned[start:end + 1]
            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        # Last resort: try the whole string
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        raise ValueError(f"Could not extract valid JSON object from LLM response: {text[:200]}")

    # ------------------------------------------------------------------
    # Fallback & response helpers (unchanged from original)
    # ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# Module-level warmup helper (call from FastAPI lifespan)
# ------------------------------------------------------------------

def warmup_llm() -> None:
    """
    Send a tiny prompt to Ollama so that the model is loaded into
    memory *before* the first real user request arrives.

    Safe to call at application startup — failures are logged and
    swallowed so they never prevent the server from starting.
    """
    base_url = os.getenv("OLLAMA_BASE_URL", _DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    model = os.getenv("OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL)
    url = f"{base_url}/api/generate"
    payload = {
        "model": model,
        "prompt": "hello",
        "stream": False,
        "keep_alive": _DEFAULT_OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0},
    }
    logger.info("event=llm_warmup phase=start model=%s", model)
    try:
        start = _time.time()
        resp = requests.post(url, json=payload, timeout=_DEFAULT_OLLAMA_TIMEOUT)
        duration = _time.time() - start
        resp.raise_for_status()
        logger.info(
            "event=llm_warmup phase=success model=%s latency=%.2fs",
            model,
            duration,
        )
    except Exception:
        logger.exception("event=llm_warmup phase=error model=%s", model)
