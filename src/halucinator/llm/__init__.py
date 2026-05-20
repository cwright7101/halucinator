"""Pluggable LLM providers for HALucinator's auto peripheral-modeler.

Swap the model/vendor via config or env with no code change:

    llm:
      provider: anthropic     # anthropic | openai | google | ollama | mock
      model: claude-opus-4-7
      base_url: null
      api_key_env: ANTHROPIC_API_KEY

    HALUCINATOR_LLM_PROVIDER=ollama HALUCINATOR_LLM_MODEL=llama3.1 ...

`get_provider` resolves the config (env overriding config) and returns a
ready provider. Concrete providers import their SDKs lazily, so importing
this package never requires any LLM SDK to be installed.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .base import LLMConfig, LLMProvider, LLMResponse

_REGISTRY = {
    "mock": ("halucinator.llm.mock", "MockProvider"),
    "anthropic": ("halucinator.llm.anthropic", "AnthropicProvider"),
    "openai": ("halucinator.llm.openai", "OpenAIProvider"),
    "google": ("halucinator.llm.google", "GoogleProvider"),
    "ollama": ("halucinator.llm.ollama", "OllamaProvider"),
}


def available_providers():
    return sorted(_REGISTRY)


def get_provider(config: Optional[Dict[str, Any]] = None) -> LLMProvider:
    """Build an LLMProvider from a config dict (env overrides win)."""
    import importlib

    cfg = LLMConfig.from_dict(config)
    if cfg.provider not in _REGISTRY:
        raise ValueError(
            f"unknown LLM provider {cfg.provider!r}; "
            f"available: {available_providers()}"
        )
    mod_name, cls_name = _REGISTRY[cfg.provider]
    module = importlib.import_module(mod_name)
    return getattr(module, cls_name)(cfg)


__all__ = [
    "LLMConfig", "LLMProvider", "LLMResponse",
    "get_provider", "available_providers",
]
