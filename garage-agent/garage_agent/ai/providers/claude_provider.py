"""
Claude LLM Provider – Anthropic (claude-3-haiku).

Extracts the system message from the OpenAI-style messages list
(Anthropic requires a separate ``system`` parameter) and passes the
remaining messages to ``messages.create``.
"""

import logging
import os

import anthropic

from garage_agent.ai.providers.base_provider import BaseLLMProvider

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude provider using the ``anthropic`` Python SDK."""

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model_name = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
        self.max_tokens = int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024"))

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required for Claude provider.")

        self.client = anthropic.Anthropic(api_key=self.api_key)

        logger.info("event=claude_provider_init model=%s", self.model_name)

    # ------------------------------------------------------------------ #
    # Interface
    # ------------------------------------------------------------------ #

    def generate(self, messages: list[dict[str, str]]) -> str:
        system_prompt, chat_messages = self._split_system_message(messages)

        logger.info(
            "event=claude_call phase=start model=%s message_count=%d",
            self.model_name,
            len(chat_messages),
        )

        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=chat_messages,
        )

        reply = response.content[0].text.strip() if response.content else ""
        logger.info("event=claude_call phase=success model=%s response_length=%d", self.model_name, len(reply))

        return reply

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _split_system_message(
        messages: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]]]:
        """
        Separate the system message from conversation messages.

        Anthropic's API requires ``system`` as a top-level parameter,
        not inside the messages list.
        """
        system_parts: list[str] = []
        chat_messages: list[dict[str, str]] = []

        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append(msg.get("content", ""))
            else:
                chat_messages.append(msg)

        return "\n\n".join(system_parts), chat_messages
