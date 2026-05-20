"""Google Gemini provider. SDK imported lazily."""
from __future__ import annotations

from .base import LLMConfig, LLMProvider, LLMResponse


class GoogleProvider(LLMProvider):
    DEFAULT_MODEL = "gemini-1.5-pro"

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        self._model_obj = None

    def _get_model(self):
        if self._model_obj is None:
            try:
                import google.generativeai as genai  # noqa: WPS433 (lazy)
            except ImportError as exc:  # noqa: BLE001
                raise RuntimeError(
                    "google provider selected but 'google-generativeai' is "
                    "not installed (pip install google-generativeai), or "
                    "switch HALUCINATOR_LLM_PROVIDER."
                ) from exc
            key = self._api_key()
            if key:
                genai.configure(api_key=key)
            self._genai = genai
            self._model_obj = genai.GenerativeModel(
                self.config.model or self.DEFAULT_MODEL)
        return self._model_obj

    def complete(self, system: str, prompt: str, *, max_tokens=None,
                 temperature=None) -> LLMResponse:
        model = self._get_model()
        cfg = self._genai.types.GenerationConfig(
            max_output_tokens=max_tokens or self.config.max_tokens,
            temperature=self.config.temperature if temperature is None else temperature,
        )
        resp = model.generate_content(
            f"{system}\n\n{prompt}" if system else prompt,
            generation_config=cfg,
        )
        return LLMResponse(text=resp.text, raw=resp,
                           model=self.config.model or self.DEFAULT_MODEL)
