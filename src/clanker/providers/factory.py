"""Provider factory for constructing adapters."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from .anthropic import AnthropicLLM
from .base import LLM, STT, TTS, ImageGen
from .elevenlabs import ElevenLabsTTS
from .memegen import MemegenImage
from .openai import OpenAILLM, OpenAISTT


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for provider selection."""

    llm: str
    stt: str
    tts: str
    image: str | None = None


T = TypeVar("T")


class ProviderFactory:
    """Simple registry for v1 providers."""

    def __init__(self) -> None:
        self._llm_registry: dict[str, Callable[[], LLM]] = {
            "openai": lambda: OpenAILLM(api_key=_require_env("OPENAI_API_KEY")),
            "anthropic": lambda: AnthropicLLM(api_key=_require_env("ANTHROPIC_API_KEY")),
        }
        self._stt_registry: dict[str, Callable[[], STT]] = {
            "openai": lambda: OpenAISTT(api_key=_require_env("OPENAI_API_KEY")),
        }
        self._tts_registry: dict[str, Callable[[], TTS]] = {
            "elevenlabs": lambda: ElevenLabsTTS(
                api_key=_require_env("ELEVENLABS_API_KEY")
            ),
        }
        self._image_registry: dict[str, Callable[[], ImageGen]] = {
            "memegen": lambda: MemegenImage(),
        }

    def get_llm(self, name: str) -> LLM:
        """Return an LLM provider instance."""
        return self._get_provider(name, self._llm_registry, "llm")

    def get_stt(self, name: str) -> STT:
        """Return an STT provider instance."""
        return self._get_provider(name, self._stt_registry, "stt")

    def get_tts(self, name: str) -> TTS:
        """Return a TTS provider instance."""
        return self._get_provider(name, self._tts_registry, "tts")

    def get_image(self, name: str) -> ImageGen:
        """Return an image provider instance."""
        return self._get_provider(name, self._image_registry, "image")

    def validate(self, config: ProviderConfig) -> None:
        """Validate provider configuration and env requirements."""
        self.get_llm(config.llm)
        self.get_stt(config.stt)
        self.get_tts(config.tts)
        if config.image:
            self.get_image(config.image)

    def _get_provider(
        self,
        name: str,
        registry: Mapping[str, Callable[[], T]],
        capability: str,
    ) -> T:
        try:
            builder = registry[name]
        except KeyError as exc:
            raise ValueError(f"Unsupported {capability} provider: {name}") from exc
        return builder()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value
