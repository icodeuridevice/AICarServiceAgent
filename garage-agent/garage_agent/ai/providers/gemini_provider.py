"""
Gemini LLM Provider – Google GenAI (gemini-1.5-flash).

Converts OpenAI-style messages into a single prompt string and calls
the Gemini ``generate_content`` API via the ``google-genai`` SDK.
"""

import logging
import os

from google import genai
from google.genai import types

from garage_agent.ai.providers.base_provider import BaseLLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider using the ``google-genai`` SDK."""

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required for Gemini provider.")

        self.client = genai.Client(api_key=self.api_key)

        logger.info("event=gemini_provider_init model=%s", self.model_name)

    # ------------------------------------------------------------------ #
    # Interface
    # ------------------------------------------------------------------ #

    def generate(self, messages: list[dict[str, str]]) -> str:
        # Separate system instruction from conversation messages
        system_instruction, contents = self._split_messages(messages)

        logger.info("event=gemini_call phase=start model=%s content_parts=%d", self.model_name, len(contents))

        config = types.GenerateContentConfig(
            temperature=0,
            system_instruction=system_instruction if system_instruction else None,
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=config,
        )

        reply = response.text.strip() if response.text else ""
        logger.info("event=gemini_call phase=success model=%s response_length=%d", self.model_name, len(reply))

        return reply

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _split_messages(
        messages: list[dict[str, str]],
    ) -> tuple[str, list[types.Content]]:
        """
        Convert OpenAI-style messages to Gemini Content objects.

        Extracts system messages as a separate system instruction,
        and maps user/assistant messages to Gemini roles.
        """
        system_parts: list[str] = []
        contents: list[types.Content] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_parts.append(content)
            elif role == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part(text=content)]))
            else:
                contents.append(types.Content(role="user", parts=[types.Part(text=content)]))

        return "\n\n".join(system_parts), contents
