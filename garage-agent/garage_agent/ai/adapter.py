from garage_agent.core.config import settings
from garage_agent.ai.rule_engine import RuleEngine
from garage_agent.ai.llm_engine import LLMEngine


def get_ai_engine():
    engine_type = settings.AI_ENGINE

    if engine_type == "rule":
        return RuleEngine()

    if engine_type == "llm":
        return LLMEngine()

    raise ValueError(f"Unsupported AI engine type: {engine_type}")