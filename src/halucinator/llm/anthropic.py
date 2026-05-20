"""Anthropic (Claude) provider. SDK imported lazily."""
from __future__ import annotations

from typing import Optional

from .base import LLMConfig, LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    DEFAULT_MODEL = "claude-opus-4-7"

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic  # noqa: WPS433 (lazy)
            except ImportError as exc:  # noqa: BLE001
                raise RuntimeError(
                    "anthropic provider selected but the 'anthropic' package "
                    "is not installed (pip install anthropic), or switch "
                    "HALUCINATOR_LLM_PROVIDER."
                ) from exc
            kwargs = {}
            key = self._api_key()
            if key:
                kwargs["api_key"] = key
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def complete(self, system: str, prompt: str, *, max_tokens=None,
                 temperature=None) -> LLMResponse:
        client = self._get_client()
        model = self.config.model or self.DEFAULT_MODEL
        msg = client.messages.create(
            model=model,
            system=system,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=self.config.temperature if temperature is None else temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )
        return LLMResponse(text=text, raw=msg, model=model)
