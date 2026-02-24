from abc import ABC, abstractmethod


class BaseAIEngine(ABC):
    """Abstract base AI engine."""

    @abstractmethod
    def process_message(self, message: str, context: dict) -> dict:
        """
        Process an incoming message and return structured intent output.

        Must return a dict with structured fields understood by the system.
        """
        raise NotImplementedError