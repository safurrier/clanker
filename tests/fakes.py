"""Fakes for testing Clanker."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from clanker.models import Context, Message
from clanker.providers.base import LLM, STT, TTS, ImageGen, StructuredLLM

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class FakeLLM(LLM, StructuredLLM):
    """Deterministic LLM fake with structured output support.

    For structured outputs, set reply_text to the JSON representation
    of the expected model, or set structured_response directly.
    """

    reply_text: str = "Hello from fake"
    structured_response: BaseModel | None = None

    async def generate(
        self, context: Context, messages: list[Message], params: dict | None = None
    ) -> Message:
        return Message(role="assistant", content=self.reply_text)

    async def generate_structured(
        self,
        response_model: type[T],
        messages: list[Message],
        max_retries: int = 2,
    ) -> T:
        """Return structured response for testing.

        If structured_response is set and matches the model type, returns it.
        Otherwise parses reply_text as JSON and validates against the model.
        """
        if self.structured_response is not None:
            if isinstance(self.structured_response, response_model):
                return self.structured_response
        # Parse reply_text as JSON and create model instance
        data = json.loads(self.reply_text)
        # Handle both {"lines": [...]} and [...] formats
        if isinstance(data, list):
            data = {"lines": data}
        return response_model.model_validate(data)


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
