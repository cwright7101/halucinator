"""Ollama (local models) provider.

Talks to a local Ollama server over HTTP using only the stdlib, so it
needs no extra SDK. Point it at the server with `base_url`
(default http://localhost:11434).
"""
from __future__ import annotations

import json
import urllib.request

from .base import LLMConfig, LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    DEFAULT_MODEL = "llama3.1"
    DEFAULT_BASE = "http://localhost:11434"

    def complete(self, system: str, prompt: str, *, max_tokens=None,
                 temperature=None) -> LLMResponse:
        base = (self.config.base_url or self.DEFAULT_BASE).rstrip("/")
        model = self.config.model or self.DEFAULT_MODEL
        body = {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": self.config.temperature
                if temperature is None else temperature,
                "num_predict": max_tokens or self.config.max_tokens,
            },
        }
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{base}/api/generate", data=data,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:  # noqa: S310 (local server)
            payload = json.loads(resp.read().decode())
        return LLMResponse(text=payload.get("response", ""), raw=payload, model=model)
