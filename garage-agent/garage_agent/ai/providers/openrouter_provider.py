"""
OpenRouter LLM Provider – HTTP API.

Uses OpenRouter's OpenAI-compatible chat endpoint at
``https://openrouter.ai/api/v1/chat/completions``.
"""

import logging
import os

import requests

from garage_agent.ai.providers.base_provider import BaseLLMProvider

logger = logging.getLogger(__name__)

_OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_TIMEOUT = 120  # seconds


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter provider using direct HTTP calls."""

    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.model_name = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3-8b-instruct")

        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required for OpenRouter provider.")

        logger.info("event=openrouter_provider_init model=%s", self.model_name)

    # ------------------------------------------------------------------ #
    # Interface
    # ------------------------------------------------------------------ #

    def generate(self, messages: list[dict[str, str]]) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0,
        }

        logger.info(
            "event=openrouter_call phase=start model=%s message_count=%d",
            self.model_name,
            len(messages),
        )

        response = requests.post(
            _OPENROUTER_API_URL,
            headers=headers,
            json=payload,
            timeout=_DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        reply = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        logger.info(
            "event=openrouter_call phase=success model=%s response_length=%d",
            self.model_name,
            len(reply),
        )

        return reply
