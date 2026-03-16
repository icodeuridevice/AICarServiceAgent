"""
OpenAI LLM Provider – GPT-4o-mini (default).

Passes OpenAI-style messages directly to ``chat.completions.create``
and returns the assistant reply.
"""

import logging
import os

from openai import OpenAI

from garage_agent.ai.providers.base_provider import BaseLLMProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider using the official ``openai`` Python SDK."""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required for OpenAI provider.")

        self.client = OpenAI(api_key=self.api_key)

        logger.info("event=openai_provider_init model=%s", self.model_name)

    # ------------------------------------------------------------------ #
    # Interface
    # ------------------------------------------------------------------ #

    def generate(self, messages: list[dict[str, str]]) -> str:
        logger.info("event=openai_call phase=start model=%s message_count=%d", self.model_name, len(messages))

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0,
        )

        reply = response.choices[0].message.content.strip() if response.choices[0].message.content else ""
        logger.info("event=openai_call phase=success model=%s response_length=%d", self.model_name, len(reply))

        return reply
