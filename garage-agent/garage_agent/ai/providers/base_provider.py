"""
Base LLM Provider – abstract interface for all LLM backends.

Every concrete provider must implement ``generate(messages)`` which
accepts an OpenAI-style messages list and returns the assistant reply
as a plain string.
"""

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """Abstract base for all LLM provider implementations."""

    @abstractmethod
    def generate(self, messages: list[dict[str, str]]) -> str:
        """
        Generate a response from the LLM.

        Parameters
        ----------
        messages : list[dict]
            OpenAI-style messages list, e.g.
            [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]

        Returns
        -------
        str
            The assistant's reply as plain text.
        """
        ...
