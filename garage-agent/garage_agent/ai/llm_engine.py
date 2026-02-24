import logging

logger = logging.getLogger(__name__)


class LLMEngine:
    """
    Future LLM-powered AI engine.
    Currently stubbed for safe integration testing.
    """

    def process(self, phone: str, message: str) -> dict:
        logger.info("LLM Engine invoked for %s", phone)

        # For now, simulate structured AI output
        return {
            "engine": "llm",
            "intent": "booking_flow",
            "confidence": 0.95,
            "raw_message": message,
        }