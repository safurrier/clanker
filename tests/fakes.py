"""Fakes for testing Clanker."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel

from clanker.models import Context, Interaction, Message, Outcome
from clanker.providers.base import LLM, STT, TTS, ImageGen, StructuredLLM
from clanker.providers.feedback import FeedbackStore

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

    async def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate_hz: int = 16000,
        params: dict | None = None,
    ) -> str:
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


@dataclass
class FakeFeedbackStore(FeedbackStore):
    """In-memory feedback store for testing.

    Note: Not frozen because we need to mutate the interactions list.
    """

    interactions: list[Interaction] = field(default_factory=list)

    async def record(self, interaction: Interaction) -> None:
        """Record an interaction in memory."""
        self.interactions.append(interaction)

    async def get_user_stats(
        self,
        user_id: str,
        context_id: str | None = None,
        command: str | None = None,
    ) -> Mapping[Outcome, int]:
        """Get outcome counts for a user."""
        counts: dict[Outcome, int] = dict.fromkeys(Outcome, 0)
        for interaction in self.interactions:
            if interaction.user_id != user_id:
                continue
            if context_id is not None and interaction.context_id != context_id:
                continue
            if command is not None and interaction.command != command:
                continue
            counts[interaction.outcome] += 1
        return counts

    async def get_recent_interactions(
        self,
        user_id: str,
        context_id: str | None = None,
        command: str | None = None,
        limit: int = 100,
    ) -> Sequence[Interaction]:
        """Get recent interactions in reverse chronological order."""
        filtered = [
            i
            for i in self.interactions
            if i.user_id == user_id
            and (context_id is None or i.context_id == context_id)
            and (command is None or i.command == command)
        ]
        # Sort by created_at descending
        filtered.sort(key=lambda i: i.created_at, reverse=True)
        return filtered[:limit]

    async def get_acceptance_rate(
        self,
        user_id: str,
        command: str,
        context_id: str | None = None,
    ) -> float:
        """Calculate acceptance rate for a user/command."""
        stats = await self.get_user_stats(user_id, context_id, command)
        # Exclude timeouts from calculation
        total = (
            stats[Outcome.ACCEPTED]
            + stats[Outcome.REJECTED]
            + stats[Outcome.REGENERATED]
        )
        if total == 0:
            return 0.5
        return stats[Outcome.ACCEPTED] / total


@dataclass
class FailingFeedbackStore(FeedbackStore):
    """Feedback store that always fails, for testing error handling."""

    async def record(self, interaction: Interaction) -> None:
        """Always raise an error."""
        raise RuntimeError("Simulated storage failure")

    async def get_user_stats(
        self,
        user_id: str,
        context_id: str | None = None,
        command: str | None = None,
    ) -> Mapping[Outcome, int]:
        """Always raise an error."""
        raise RuntimeError("Simulated storage failure")

    async def get_recent_interactions(
        self,
        user_id: str,
        context_id: str | None = None,
        command: str | None = None,
        limit: int = 100,
    ) -> Sequence[Interaction]:
        """Always raise an error."""
        raise RuntimeError("Simulated storage failure")

    async def get_acceptance_rate(
        self,
        user_id: str,
        command: str,
        context_id: str | None = None,
    ) -> float:
        """Always raise an error."""
        raise RuntimeError("Simulated storage failure")
