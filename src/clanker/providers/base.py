"""Base protocols for providers."""

from __future__ import annotations

from typing import Protocol

from ..models import Context, Message


class LLM(Protocol):
    """Protocol for LLM providers."""

    async def generate(
        self, context: Context, messages: list[Message], params: dict | None = None
    ) -> Message:
        """Generate a response from the LLM."""
        ...


class STT(Protocol):
    """Protocol for speech-to-text providers."""

    async def transcribe(self, audio_bytes: bytes, params: dict | None = None) -> str:
        """Transcribe audio bytes to text."""
        ...


class TTS(Protocol):
    """Protocol for text-to-speech providers."""

    async def synthesize(
        self, text: str, voice: str, params: dict | None = None
    ) -> bytes:
        """Synthesize text to audio bytes."""
        ...


class ImageGen(Protocol):
    """Protocol for image generation providers."""

    async def generate(self, params: dict) -> bytes | str:
        """Generate an image from parameters."""
        ...
