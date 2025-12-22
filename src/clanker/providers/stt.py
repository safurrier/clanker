"""STT provider protocol."""

from __future__ import annotations

from typing import Protocol


class STT(Protocol):
    """Speech-to-text interface."""

    async def transcribe(self, audio_bytes: bytes, params: dict | None = None) -> str:
        """Transcribe audio bytes to text."""
