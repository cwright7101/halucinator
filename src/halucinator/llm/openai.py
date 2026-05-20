"""OpenAI / Azure-OpenAI-compatible provider. SDK imported lazily.

Also serves any OpenAI-compatible endpoint (vLLM, LM Studio, etc.) via
`base_url`.
"""
from __future__ import annotations

from .base import LLMConfig, LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    DEFAULT_MODEL = "gpt-4o"

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import openai  # noqa: WPS433 (lazy)
            except ImportError as exc:  # noqa: BLE001
                raise RuntimeError(
                    "openai provider selected but the 'openai' package is not "
                    "installed (pip install openai), or switch "
                    "HALUCINATOR_LLM_PROVIDER."
                ) from exc
            kwargs = {}
            key = self._api_key()
            if key:
                kwargs["api_key"] = key
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = openai.OpenAI(**kwargs)
        return self._client

    def complete(self, system: str, prompt: str, *, max_tokens=None,
                 temperature=None) -> LLMResponse:
        client = self._get_client()
        model = self.config.model or self.DEFAULT_MODEL
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=self.config.temperature if temperature is None else temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        text = resp.choices[0].message.content or ""
        return LLMResponse(text=text, raw=resp, model=model)
