"""
LLM Engine – Agentic Execution Layer (Ollama / qwen3.5:2b).

Responsible for:
1. Understanding user intent (LLM or rule fallback)
2. Requesting tool definitions from ToolRegistry
3. Executing selected tools via registry
4. Returning structured response payload

Provider: local Ollama instance (HTTP POST to /api/generate).
"""

import json
import logging
import os
import subprocess
import time as _time
from datetime import date, datetime, time, timedelta
from typing import Any

import requests
from sqlalchemy.orm import Session

from garage_agent.ai.base_engine import BaseEngine
from garage_agent.ai.rule_engine import RuleEngine
from garage_agent.ai.tools.registry import ToolRegistry
from garage_agent.services import booking_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------
_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
_DEFAULT_OLLAMA_GENERATE_PATH = "/api/generate"
_DEFAULT_OLLAMA_TAGS_PATH = "/api/tags"
MODEL_NAME = "qwen3.5:2b"
_DEFAULT_OLLAMA_MODEL = MODEL_NAME
_DEFAULT_OLLAMA_TIMEOUT = 300  # seconds
_DEFAULT_OLLAMA_NUM_PREDICT = 120
_MODEL_CHECK_TTL_SECONDS = 60
_SIMPLE_MESSAGES = ["hi", "hello", "hey"]
_DEFAULT_BOOKING_TIME = time(10, 0)

_model_check_cache: dict[str, float] = {}


def _normalize_ollama_base_url(raw_base_url: str) -> str:
    normalized = (raw_base_url or _DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")
    if normalized.endswith(_DEFAULT_OLLAMA_GENERATE_PATH):
        normalized = normalized[: -len(_DEFAULT_OLLAMA_GENERATE_PATH)]
    return normalized or _DEFAULT_OLLAMA_BASE_URL


def _build_generate_url(base_url: str) -> str:
    return f"{base_url}{_DEFAULT_OLLAMA_GENERATE_PATH}"


def _build_tags_url(base_url: str) -> str:
    return f"{base_url}{_DEFAULT_OLLAMA_TAGS_PATH}"


def _ensure_ollama_server_available(base_url: str) -> None:
    url = _build_tags_url(base_url)
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Ollama server not available")
        logger.warning(
            "event=ollama_health_check phase=error url=%s error=%s",
            url,
            str(exc)[:300],
        )
        raise RuntimeError("Ollama server not available") from exc


def _ensure_ollama_model_available(model: str) -> None:
    now = _time.time()
    last_checked = _model_check_cache.get(model)
    if last_checked and (now - last_checked) < _MODEL_CHECK_TTL_SECONDS:
        return

    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except FileNotFoundError as exc:
        logger.error(
            "event=ollama_model_check phase=command_missing model=%s error=%s",
            model,
            exc,
        )
        raise RuntimeError("Ollama CLI not found. Install Ollama and ensure `ollama` is on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        logger.error("event=ollama_model_check phase=timeout model=%s", model)
        raise RuntimeError("Timed out while running `ollama list`.") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        logger.error(
            "event=ollama_model_check phase=command_error model=%s return_code=%s stderr=%s",
            model,
            result.returncode,
            stderr[:300],
        )
        raise RuntimeError(f"`ollama list` failed with return code {result.returncode}.")

    available_models: set[str] = set()
    for line in (result.stdout or "").splitlines():
        parts = line.split()
        if not parts:
            continue
        first_token = parts[0].strip()
        if first_token.lower() in {"name", "model"}:
            continue
        available_models.add(first_token)

    if model not in available_models:
        logger.error(
            "event=ollama_model_check phase=missing model=%s available_models=%s",
            model,
            sorted(available_models),
        )
        raise RuntimeError(
            f"Ollama model '{model}' is not available. Run `ollama pull {model}`."
        )

    _model_check_cache[model] = now


def select_relevant_tools(message: str) -> list[str]:
    message = (message or "").lower()

    if "book" in message or "service" in message:
        return ["create_booking"]

    if "reschedule" in message:
        return ["reschedule_booking"]

    if "cancel" in message:
        return ["cancel_booking"]

    if "job card" in message:
        return ["create_jobcard"]

    if "complete job" in message:
        return ["complete_jobcard"]

    if "summary" in message:
        return ["daily_summary"]

    return []


class LLMEngine(BaseEngine):
    def __init__(self):
        self._registry: ToolRegistry | None = None
        self.rule_engine = RuleEngine()
        self.provider = (os.getenv("LLM_PROVIDER", "ollama") or "ollama").strip().lower()

        self.ollama_base_url = _normalize_ollama_base_url(
            os.getenv("OLLAMA_BASE_URL", _DEFAULT_OLLAMA_BASE_URL)
        )
        self.model = os.getenv("OLLAMA_MODEL", MODEL_NAME)

        self.system_prompt = (
            "You are a garage service assistant. "
            "Pick one backend tool when needed. "
            "If required details are missing, ask one short question."
        )
        self.tool_result_prompt = (
            "A garage backend tool already ran successfully. "
            "Write a short customer-friendly WhatsApp reply from the tool result. "
            "Do not mention internal implementation details."
        )
        self.tool_execution_failure_reply = "I couldn't complete that request. Please try again."

        logger.info(
            "event=llm_engine_init provider=%s model=%s base_url=%s",
            self.provider,
            self.model,
            self.ollama_base_url,
        )

    # ------------------------------------------------------------------
    # Ollama HTTP transport
    # ------------------------------------------------------------------

    @property
    def registry(self) -> ToolRegistry:
        if self._registry is None:
            self._registry = ToolRegistry()
        return self._registry

    def _call_ollama(
        self,
        prompt: str,
        *,
        model: str | None = None,
        num_predict: int = _DEFAULT_OLLAMA_NUM_PREDICT,
    ) -> str:
        """
        Send a prompt to the local Ollama instance and return the
        generated text. Uses ``/api/generate`` with streaming disabled
        and deterministic decoding tuned for CPU inference.

        Performance knobs (CPU-friendly):
        * ``num_predict`` – bounds token generation cost.
        * ``timeout``    – keep latency bounded for webhook UX.
        * Latency is measured and logged on every call.
        """
        logger.info("event=ollama_prompt_size tokens=%s", len(prompt))
        _ensure_ollama_server_available(self.ollama_base_url)
        target_model = model or self.model
        _ensure_ollama_model_available(target_model)
        url = _build_generate_url(self.ollama_base_url)
        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "temperature": 0,
            "num_predict": num_predict,
            "think": False,
        }
        logger.info("event=ollama_call phase=start url=%s model=%s", url, target_model)

        start = _time.time()
        response = requests.post(url, json=payload, timeout=_DEFAULT_OLLAMA_TIMEOUT)
        duration = _time.time() - start

        response.raise_for_status()
        data = response.json()
        generated_text = data.get("response", "").strip()
        logger.info(
            "event=ollama_call phase=success model=%s response_length=%d latency=%.2fs",
            target_model,
            len(generated_text),
            duration,
        )
        return generated_text

    def _call_model(
        self,
        prompt: str,
        *,
        model: str | None = None,
        num_predict: int = _DEFAULT_OLLAMA_NUM_PREDICT,
    ) -> str:
        if self.provider == "ollama":
            return self._call_ollama(prompt, model=model, num_predict=num_predict)
        raise RuntimeError(f"Unsupported LLM provider: {self.provider}")

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_booking_extraction_prompt(self, message: str) -> str:
        return f"""
Extract booking information from the message.

User message:
{message}

Return JSON with fields:

vehicle
service
date
time

If information is missing, return null.

Example output:

{{
"vehicle": "Audi",
"service": "general service",
"date": null,
"time": null
}}

Only return JSON.
"""

    def _build_tool_selection_prompt(self, user_message: str, tool_definitions: list[str]) -> str:
        """
        Constructs a prompt that asks the LLM to decide whether a tool
        should be called or a conversational reply should be returned.

        The model is instructed to reply with **only** a JSON object in
        one of two shapes:

        Tool call:
            {"action": "<tool_name>", "arg1": "...", ...}

        Conversation (no tool needed):
            {"action": "conversation", "reply": "..."}
        """
        tool_descriptions = self._get_tool_description_block(tool_definitions)

        prompt = (
            f"### SYSTEM\n{self.system_prompt}\n\n"
            f"### AVAILABLE TOOLS\n{tool_descriptions}\n\n"
            "### INSTRUCTIONS\n"
            "Choose one action for the user message.\n"
            "- Tool action: return JSON with \"action\"=<tool_name> and required args.\n"
            "- Conversation action: return JSON {\"action\":\"conversation\",\"reply\":\"<text>\"}\n\n"
            "Rules:\n"
            "1. Respond with one valid JSON object only (no markdown, no explanation).\n"
            "2. Use the exact tool names listed above.\n"
            "3. Keep keys minimal; include only required arguments.\n"
            "4. Dates must be YYYY-MM-DD, times HH:MM (24-hour).\n"
            "5. If required info is missing, ask a short clarifying question.\n\n"
            f"### USER MESSAGE\n{user_message}\n\n"
            "### YOUR JSON RESPONSE\n"
        )
        return prompt

    def _get_tool_description_block(self, tool_definitions: list[str]) -> str:
        """
        Return a compact list of available tool names.

        Minimised to reduce token count for CPU-constrained inference;
        the model only needs to know *which* tools exist — the backend
        handles argument validation via ToolRegistry.
        """
        if not tool_definitions:
            return "No tools available."
        # Plain newline-separated list — cheapest possible representation
        return "\n".join(f"- {name}" for name in tool_definitions)

    @staticmethod
    def _is_simple_message(message: str) -> bool:
        return message.lower().strip() in _SIMPLE_MESSAGES

    def _get_tool_definitions_for_message(self, message: str) -> list[str]:
        tool_names = select_relevant_tools(message)
        logger.info("event=tool_router selected_tools=%s", tool_names)
        if not tool_names:
            logger.info("event=tool_registry phase=skipped reason=no_relevant_tools")
            return []

        tool_definitions = self.registry.get_tools(tool_names)
        logger.info(
            "event=tool_registry phase=loaded tool_count=%s",
            len(tool_definitions),
        )
        return tool_definitions

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
            f"### SYSTEM\n{self.tool_result_prompt}\n\n"
            f"### ORIGINAL USER MESSAGE\n{user_message}\n\n"
            f"### EXECUTED TOOL\n{tool_name}\n\n"
            f"### TOOL RESULT (JSON)\n{tool_result_payload}\n\n"
            "### INSTRUCTIONS\n"
            "Reply in plain text only. Keep it concise (max 2 short sentences). "
            "Do not output JSON.\n"
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

        if self._is_simple_message(safe_message):
            logger.info("event=simple_router phase=matched engine=rule")
            return self._response_contract(
                engine="rule",
                response_type="conversation",
                reply="Hello! How can I assist you with your car service today?",
                tool=None,
                arguments=None,
                result=None,
            )

        # ----- Step 1: Router selects tool -----
        selected_tools = self._get_tool_definitions_for_message(safe_message)
        if not selected_tools:
            return self._fallback_to_rule(
                db=db,
                garage_id=garage_id,
                phone=phone,
                message=safe_message,
                reason="no_tool_selected",
            )

        tool_name = selected_tools[0]
        if tool_name != "create_booking":
            logger.info(
                "event=tool_router phase=unsupported_selected_tool tool=%s",
                tool_name,
            )
            return self._fallback_to_rule(
                db=db,
                garage_id=garage_id,
                phone=phone,
                message=safe_message,
                reason="unsupported_selected_tool",
            )

        # ----- Step 2: Prompt model for argument extraction only -----
        extraction_prompt = self._build_booking_extraction_prompt(safe_message)
        try:
            logger.info("event=model_call phase=start mode=booking_extraction model=%s", MODEL_NAME)
            raw_response = self._call_model(
                extraction_prompt,
                model=MODEL_NAME,
                num_predict=80,
            )
            logger.info("event=model_call phase=success mode=booking_extraction model=%s", MODEL_NAME)
        except Exception as exc:
            logger.exception("event=model_call phase=error mode=booking_extraction model=%s", MODEL_NAME)
            return self._fallback_to_rule(
                db=db,
                garage_id=garage_id,
                phone=phone,
                message=safe_message,
                reason="ollama_api_error",
                error=exc,
            )

        # ----- Step 3: Parse JSON arguments -----
        try:
            extracted_arguments = self._parse_booking_extraction_arguments(raw_response)
        except ValueError as exc:
            logger.warning(
                "event=model_call phase=json_parse_error mode=booking_extraction raw_response=%s",
                raw_response[:300],
            )
            return self._fallback_to_rule(
                db=db,
                garage_id=garage_id,
                phone=phone,
                message=safe_message,
                reason="ollama_json_parse_error",
                error=exc,
            )

        # ----- Step 4/5: Execute create_booking tool -----
        logger.info("event=tool_execution phase=start tool=%s", tool_name)
        try:
            customer = booking_service.get_or_create_customer_by_phone(
                db=db,
                garage_id=garage_id,
                phone=phone,
            )
            booking_arguments = self._build_create_booking_arguments(
                extracted_arguments=extracted_arguments,
                customer_id=customer.id,
            )
            booking = booking_service.create_booking(
                db=db,
                garage_id=garage_id,
                **booking_arguments,
            )
            self._apply_vehicle_model_from_extraction(
                db=db,
                booking=booking,
                vehicle_label=extracted_arguments.get("vehicle"),
            )
        except Exception:
            logger.exception("event=tool_execution phase=error tool=%s", tool_name)
            return self._tool_execution_failure_response()

        serialized_result = self._make_json_safe(booking)
        logger.info("event=tool_execution phase=finish tool=%s success=%s", tool_name, True)

        final_reply = self._build_booking_success_reply(extracted_arguments)
        return self._response_contract(
            engine="llm",
            response_type="tool_call",
            reply=final_reply,
            tool=tool_name,
            arguments=extracted_arguments,
            result=serialized_result,
        )

    # ------------------------------------------------------------------
    # Follow-up reply generation
    # ------------------------------------------------------------------

    def _generate_tool_followup_reply(
        self,
        user_message: str,
        tool_name: str,
        tool_result: Any,
    ) -> str:
        prompt = self._build_followup_prompt(user_message, tool_name, tool_result)
        reply = self._call_model(prompt)
        return reply or "Request processed."

    @staticmethod
    def _normalize_optional_string(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return None
        if not isinstance(value, str):
            value = str(value)
        normalized = value.strip()
        return normalized or None

    def _parse_booking_extraction_arguments(self, response: str) -> dict[str, Any]:
        try:
            arguments = json.loads(response)
        except json.JSONDecodeError:
            arguments = self._extract_json(response)

        if not isinstance(arguments, dict):
            raise ValueError("LLM output is not a JSON object.")

        return {
            "vehicle": self._normalize_optional_string(arguments.get("vehicle")),
            "service": self._normalize_optional_string(arguments.get("service")),
            "date": self._normalize_optional_string(arguments.get("date")),
            "time": self._normalize_optional_string(arguments.get("time")),
        }

    @staticmethod
    def _parse_extracted_date(raw_date: str | None) -> date | None:
        if raw_date is None:
            return None

        normalized = raw_date.strip().lower()
        if not normalized:
            return None
        if normalized == "today":
            return date.today()
        if normalized == "tomorrow":
            return date.today() + timedelta(days=1)

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(normalized, fmt).date()
            except ValueError:
                continue

        current_year = date.today().year
        try:
            return datetime.strptime(f"{normalized}/{current_year}", "%d/%m/%Y").date()
        except ValueError:
            pass

        try:
            return datetime.strptime(f"{normalized}-{current_year}", "%d-%m-%Y").date()
        except ValueError:
            pass

        return None

    @staticmethod
    def _parse_extracted_time(raw_time: str | None) -> time | None:
        if raw_time is None:
            return None

        normalized = raw_time.strip().lower()
        if not normalized:
            return None
        if normalized == "noon":
            return time(12, 0)
        if normalized == "midnight":
            return time(0, 0)

        compact_time = normalized.replace(" ", "").replace(".", ":")
        for fmt in ("%H:%M", "%H", "%I:%M%p", "%I%p"):
            try:
                return datetime.strptime(compact_time, fmt).time()
            except ValueError:
                continue

        return None

    def _build_create_booking_arguments(
        self,
        extracted_arguments: dict[str, Any],
        customer_id: int,
    ) -> dict[str, Any]:
        service = self._normalize_optional_string(extracted_arguments.get("service"))
        service_type = "_".join(service.lower().split()) if service else "general_service"

        parsed_date = self._parse_extracted_date(
            self._normalize_optional_string(extracted_arguments.get("date"))
        )
        parsed_time = self._parse_extracted_time(
            self._normalize_optional_string(extracted_arguments.get("time"))
        )

        return {
            "customer_id": customer_id,
            "service_type": service_type,
            "service_date": parsed_date or date.today(),
            "service_time": parsed_time or _DEFAULT_BOOKING_TIME,
        }

    @staticmethod
    def _apply_vehicle_model_from_extraction(db: Session, booking: Any, vehicle_label: str | None) -> None:
        normalized_vehicle = vehicle_label.strip() if isinstance(vehicle_label, str) else ""
        if not normalized_vehicle:
            return

        vehicle = getattr(booking, "vehicle", None)
        if vehicle is None:
            return

        if getattr(vehicle, "vehicle_model", None) == normalized_vehicle:
            return

        vehicle.vehicle_model = normalized_vehicle
        db.commit()
        db.refresh(booking)

    @staticmethod
    def _build_booking_success_reply(extracted_arguments: dict[str, Any]) -> str:
        vehicle = extracted_arguments.get("vehicle")
        if isinstance(vehicle, str) and vehicle.strip():
            return f"Your {vehicle.strip()} service booking has been created."
        return "Your service booking has been created."

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
    base_url = _normalize_ollama_base_url(
        os.getenv("OLLAMA_BASE_URL", _DEFAULT_OLLAMA_BASE_URL)
    )
    model = os.getenv("OLLAMA_MODEL", MODEL_NAME)
    url = _build_generate_url(base_url)
    payload = {
        "model": model,
        "prompt": "hello",
        "stream": False,
        "temperature": 0,
        "num_predict": 16,
    }
    logger.info("event=llm_warmup phase=start model=%s", model)
    try:
        _ensure_ollama_server_available(base_url)
        _ensure_ollama_model_available(model)
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
