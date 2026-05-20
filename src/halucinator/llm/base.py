"""Pluggable LLM provider abstraction.

The auto peripheral-model generator uses an LLM for the *semantic* step
(reading register meaning out of a datasheet/SVD/disassembly, proposing a
return policy). The provider is reached through this thin ABC so the
model / vendor can be swapped with no code change, and so the package has
no hard dependency on any one LLM SDK — each concrete provider imports its
SDK lazily, and the `mock` provider needs none.

Selection is config- and env-driven; see `get_provider`.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LLMResponse:
    """Normalised response across providers."""
    text: str
    raw: Any = None
    model: str = ""


@dataclass
class LLMConfig:
    provider: str = "mock"
    model: str = ""
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "LLMConfig":
        """Build from a config dict, with env overrides taking precedence so
        CI / local can swap provider/model without editing config files."""
        d = dict(d or {})
        cfg = cls(
            provider=d.get("provider", "mock"),
            model=d.get("model", ""),
            base_url=d.get("base_url"),
            api_key_env=d.get("api_key_env"),
            max_tokens=int(d.get("max_tokens", 4096)),
            temperature=float(d.get("temperature", 0.0)),
            extra={k: v for k, v in d.items() if k not in (
                "provider", "model", "base_url", "api_key_env",
                "max_tokens", "temperature")},
        )
        # Env overrides win.
        cfg.provider = os.environ.get("HALUCINATOR_LLM_PROVIDER", cfg.provider)
        cfg.model = os.environ.get("HALUCINATOR_LLM_MODEL", cfg.model)
        cfg.base_url = os.environ.get("HALUCINATOR_LLM_BASE_URL", cfg.base_url)
        return cfg


class LLMProvider(ABC):
    """A minimal text-completion interface. Concrete providers translate
    `complete` onto their vendor SDK; the SDK is imported lazily inside
    the provider so importing this package never requires it."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def _api_key(self) -> Optional[str]:
        if self.config.api_key_env:
            return os.environ.get(self.config.api_key_env)
        return None

    @abstractmethod
    def complete(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        """Return a single completion for (system, prompt)."""

    @property
    def name(self) -> str:
        return f"{self.config.provider}:{self.config.model or '<default>'}"
