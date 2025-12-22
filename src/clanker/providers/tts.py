"""TTS provider protocol."""

from __future__ import annotations

from typing import Protocol


class TTS(Protocol):
    """Text-to-speech interface."""

    async def synthesize(
        self, text: str, voice: str | None, params: dict | None = None
    ) -> bytes:
        """Synthesize audio from text."""
