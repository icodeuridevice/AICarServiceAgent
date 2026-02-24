"""
AI Adapter – Switch between RuleEngine and LLMEngine.
"""

import os

from garage_agent.ai.rule_engine import RuleEngine
from garage_agent.ai.llm_engine import LLMEngine


def get_ai_engine():
    engine_type = os.getenv("AI_ENGINE", "rule")

    if engine_type == "llm":
        return LLMEngine()

    return RuleEngine()