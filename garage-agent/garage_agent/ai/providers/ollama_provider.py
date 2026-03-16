"""
Ollama LLM Provider – local Ollama instance.

Preserves the existing retry logic, exponential backoff, keep_alive,
and num_predict support from the original ``_call_ollama`` method.
"""

import logging
import os
import time as _time

import requests

from garage_agent.ai.providers.base_provider import BaseLLMProvider

logger = logging.getLogger(__name__)

_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
_DEFAULT_OLLAMA_MODEL = "qwen3.5:0.8b"
_DEFAULT_OLLAMA_TIMEOUT = 300          # seconds – generous for CPU inference
_DEFAULT_OLLAMA_KEEP_ALIVE = "30m"     # keep model resident in RAM
_DEFAULT_OLLAMA_RETRIES = 2            # retry count for transient failures
_DEFAULT_OLLAMA_NUM_PREDICT = 120


class OllamaProvider(BaseLLMProvider):
    """Local Ollama provider using HTTP calls to ``/api/chat``."""

    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", _DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL)

        logger.info("event=ollama_provider_init model=%s base_url=%s", self.model, self.base_url)

    # ------------------------------------------------------------------ #
    # Interface
    # ------------------------------------------------------------------ #

    def generate(self, messages: list[dict[str, str]]) -> str:
        """
        Send chat messages to the local Ollama instance and return the
        generated assistant text.

        Uses ``/api/chat`` with streaming disabled and temperature fixed
        at 0 for deterministic output.  Includes automatic retry with
        exponential backoff for transient failures.
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": _DEFAULT_OLLAMA_NUM_PREDICT,
            },
            "think": False,
            "keep_alive": _DEFAULT_OLLAMA_KEEP_ALIVE,
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
                    "event=ollama_call phase=success model=%s message_count=%d "
                    "response_length=%d latency=%.2fs attempt=%d",
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
                    _time.sleep(min(2 ** attempt, 4))

        # All retries exhausted
        raise last_error  # type: ignore[misc]

    # ------------------------------------------------------------------ #
    # Warmup helper
    # ------------------------------------------------------------------ #

    def warmup(self) -> None:
        """
        Send a tiny prompt so the model is loaded into RAM before the
        first real user request.  Failures are logged and swallowed.
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": "hello",
            "stream": False,
            "keep_alive": _DEFAULT_OLLAMA_KEEP_ALIVE,
            "options": {"temperature": 0},
        }
        logger.info("event=ollama_warmup phase=start model=%s", self.model)
        try:
            start = _time.time()
            resp = requests.post(url, json=payload, timeout=_DEFAULT_OLLAMA_TIMEOUT)
            duration = _time.time() - start
            resp.raise_for_status()
            logger.info(
                "event=ollama_warmup phase=success model=%s latency=%.2fs",
                self.model,
                duration,
            )
        except Exception:
            logger.exception("event=ollama_warmup phase=error model=%s", self.model)
