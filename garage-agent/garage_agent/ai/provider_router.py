"""
Provider Router – dynamically selects the LLM provider based on the
``LLM_PROVIDER`` environment variable.

Supported values:
    gemini | openai | claude | openrouter | ollama (default)
"""

import logging
import os

from garage_agent.ai.providers.base_provider import BaseLLMProvider

logger = logging.getLogger(__name__)

_PROVIDER_REGISTRY: dict[str, str] = {
    "gemini":     "garage_agent.ai.providers.gemini_provider.GeminiProvider",
    "openai":     "garage_agent.ai.providers.openai_provider.OpenAIProvider",
    "claude":     "garage_agent.ai.providers.claude_provider.ClaudeProvider",
    "openrouter": "garage_agent.ai.providers.openrouter_provider.OpenRouterProvider",
    "ollama":     "garage_agent.ai.providers.ollama_provider.OllamaProvider",
}

_cached_provider: BaseLLMProvider | None = None


def get_provider() -> BaseLLMProvider:
    """
    Return the configured LLM provider instance.

    The provider is lazily instantiated on first call and cached for
    subsequent calls (singleton per process).
    """
    global _cached_provider
    if _cached_provider is not None:
        return _cached_provider

    provider_name = os.getenv("LLM_PROVIDER", "ollama").lower().strip()

    dotted_path = _PROVIDER_REGISTRY.get(provider_name)
    if dotted_path is None:
        supported = ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider_name}'. Supported: {supported}"
        )

    # Lazy import to avoid loading all SDKs at startup
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    provider_class = getattr(module, class_name)

    _cached_provider = provider_class()
    logger.info(
        "event=provider_router provider=%s class=%s",
        provider_name,
        class_name,
    )
    return _cached_provider


def get_provider_name() -> str:
    """Return the currently configured provider name (lowercase)."""
    return os.getenv("LLM_PROVIDER", "ollama").lower().strip()
