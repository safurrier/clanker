"""Fakes for testing Clanker."""

from __future__ import annotations

from dataclasses import dataclass

from clanker.models import Context, Message
from clanker.providers.base import ImageGen, LLM, STT, TTS


@dataclass(frozen=True)
class FakeLLM(LLM):
    """Deterministic LLM fake."""

    reply_text: str = "Hello from fake"

    async def generate(
        self, context: Context, messages: list[Message], params: dict | None = None
    ) -> Message:
        return Message(role="assistant", content=self.reply_text)


@dataclass(frozen=True)
class FakeSTT(STT):
    """Deterministic STT fake."""

    transcript: str = "transcript"

    async def transcribe(self, audio_bytes: bytes, params: dict | None = None) -> str:
        return self.transcript


@dataclass(frozen=True)
class FakeTTS(TTS):
    """Deterministic TTS fake."""

    audio_bytes: bytes = b"audio"

    async def synthesize(
        self, text: str, voice: str, params: dict | None = None
    ) -> bytes:
        return self.audio_bytes


@dataclass(frozen=True)
class FakeImage(ImageGen):
    """Deterministic image generation fake."""

    image_bytes: bytes = b"image"

    async def generate(self, params: dict) -> bytes:
        return self.image_bytes
