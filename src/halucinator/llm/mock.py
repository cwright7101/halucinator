"""Deterministic mock LLM provider.

Needs no SDK, network, or API key, so the modeling pipeline and its tests
run in CI without external dependencies. Returns canned/echo responses,
optionally overridable via a callable for targeted unit tests.
"""
from __future__ import annotations

from typing import Callable, Optional

from .base import LLMConfig, LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    def __init__(self, config: LLMConfig,
                 responder: Optional[Callable[[str, str], str]] = None) -> None:
        super().__init__(config)
        self._responder = responder

    def complete(self, system: str, prompt: str, *, max_tokens=None,
                 temperature=None) -> LLMResponse:
        if self._responder is not None:
            text = self._responder(system, prompt)
        else:
            # Deterministic, content-free stub: echoes a compact marker so
            # callers can assert the pipeline ran without asserting on model
            # output.
            text = "MOCK_LLM_RESPONSE"
        return LLMResponse(text=text, raw=None, model=self.config.model or "mock")
