from sqlalchemy.orm import Session

from garage_agent.ai.base_engine import BaseEngine


class RuleEngine(BaseEngine):
    """
    Default AI engine (rule-based).
    Future LLM engine will implement same interface.
    """

    def process(self, db: Session, phone: str, message: str) -> dict:
        """
        Process incoming message.
        Currently returns structured metadata only.
        """
        return {
            "engine": "rule",
            "type": "conversation",
            "reply": "Request processed.",
            "tool": None,
            "result": None,
        }
