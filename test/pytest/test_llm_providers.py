"""Tests for the pluggable LLM provider layer (halucinator.llm)."""
import os

import pytest

from halucinator.llm import available_providers, get_provider
from halucinator.llm.base import LLMConfig
from halucinator.llm.mock import MockProvider


def test_all_providers_registered():
    for name in ("anthropic", "openai", "google", "ollama", "mock"):
        assert name in available_providers()


def test_mock_provider_default():
    p = get_provider({"provider": "mock", "model": "x"})
    assert isinstance(p, MockProvider)
    assert p.name == "mock:x"
    assert p.complete("sys", "hi").text == "MOCK_LLM_RESPONSE"


def test_mock_custom_responder():
    m = MockProvider(LLMConfig(provider="mock"),
                     responder=lambda s, u: f"R:{u}")
    assert m.complete("s", "abc").text == "R:abc"


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        get_provider({"provider": "does-not-exist"})


def test_env_overrides_config(monkeypatch):
    monkeypatch.setenv("HALUCINATOR_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("HALUCINATOR_LLM_MODEL", "llama3.1")
    monkeypatch.setenv("HALUCINATOR_LLM_BASE_URL", "http://x:1")
    p = get_provider({"provider": "mock", "model": "ignored"})
    assert p.config.provider == "ollama"
    assert p.config.model == "llama3.1"
    assert p.config.base_url == "http://x:1"


def test_importing_package_requires_no_sdk():
    # Importing the package and constructing real providers must not import
    # any vendor SDK (lazy import). Constructing is fine; only .complete or
    # client access triggers the SDK.
    import halucinator.llm.anthropic as a
    import halucinator.llm.openai as o
    import halucinator.llm.google as g
    for mod, cls in ((a, "AnthropicProvider"), (o, "OpenAIProvider"),
                     (g, "GoogleProvider")):
        getattr(mod, cls)(LLMConfig(provider="x"))  # no SDK needed to build


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret123")
    cfg = LLMConfig(provider="mock", api_key_env="MY_KEY")
    p = MockProvider(cfg)
    assert p._api_key() == "secret123"
