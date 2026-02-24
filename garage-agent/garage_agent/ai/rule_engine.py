from garage_agent.ai.base import BaseAIEngine
from garage_agent.services.extractor import extract_booking_details
from garage_agent.services.conversation_service import (
    get_state,
    set_state,
)

class RuleEngine:
    """
    Default AI engine (rule-based).
    Future LLM engine will implement same interface.
    """

    def process(self, phone: str, message: str) -> dict:
        """
        Process incoming message.
        Currently returns structured metadata only.
        """
        return {
            "engine": "rule",
            "intent": "booking_flow",
            "confidence": 1.0,
        }