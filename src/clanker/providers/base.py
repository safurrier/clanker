"""Base protocols for providers."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from ..models import Context, Message

T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    """Protocol for LLM providers."""

    async def generate(
        self, context: Context, messages: list[Message], params: dict | None = None
    ) -> Message:
        """Generate a response from the LLM."""
        ...


@runtime_checkable
class StructuredLLM(Protocol):
    """Protocol for LLMs supporting structured outputs via Pydantic models.

    Structured outputs guarantee the response matches the provided schema.
    Implemented using the Instructor library internally.

    This is a separate protocol from LLM to allow gradual adoption -
    not all LLM implementations need to support structured outputs.
    """

    async def generate_structured(
        self,
        response_model: type[T],
        messages: list[Message],
        max_retries: int = 2,
    ) -> T:
        """Generate a structured response matching the Pydantic model.

        Args:
            response_model: Pydantic model class defining the output schema
            messages: Conversation messages to send to the LLM
            max_retries: Number of retries if validation fails (default: 2)

        Returns:
            Instance of response_model with validated data
        """
        ...


class STT(Protocol):
    """Protocol for speech-to-text providers."""

    async def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate_hz: int = 16000,
        params: dict | None = None,
    ) -> str:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: WAV audio bytes to transcribe
            sample_rate_hz: Sample rate of the audio in Hz. Providers may
                resample internally if they require a specific rate.
            params: Optional provider-specific parameters

        Returns:
            Transcribed text
        """
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
