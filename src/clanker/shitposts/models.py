"""Models for shitpost templates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ShitpostTemplate:
    """Template for a shitpost prompt."""

    name: str
    category: str
    prompt: str
    tags: Sequence[str]


@dataclass(frozen=True)
class ShitpostRequest:
    """Request for a shitpost generation."""

    template: ShitpostTemplate
    variables: Mapping[str, str]


@runtime_checkable
class Utterance(Protocol):
    """Protocol for transcript utterances.

    Duck-typed to avoid coupling shitposts module to voice module.
    Compatible with TranscriptEvent from clanker.voice.worker.
    """

    @property
    def text(self) -> str: ...

    @property
    def start_time(self) -> datetime: ...


@dataclass(frozen=True)
class ShitpostContext:
    """Context for generating contextual shitposts/memes.

    Supports multiple input sources with configurable windowing:
    - user_input: Optional explicit guidance from the user
    - messages: Recent chat messages (windowed by max_messages)
    - transcript_utterances: Voice transcript (windowed by max_transcript_minutes)

    Note: If construction logic becomes complex or varies significantly by source,
    consider adding factory methods like from_voice_channel() or from_thread().
    """

    # Optional user guidance (e.g., "make it about cats")
    user_input: str | None = None

    # Conversation context sources
    messages: tuple[Mapping[str, str], ...] | None = None
    transcript_utterances: tuple[Utterance, ...] | None = None

    # Window configuration
    max_messages: int = 10
    max_transcript_minutes: float = 5.0
    max_transcript_utterances: int = 50

    # Metadata
    channel_type: str | None = None  # "voice", "text", "thread"

    def get_prompt_input(self) -> str:
        """Build prompt input from available context.

        Priority order:
        1. User input (if provided, used as primary subject)
        2. Windowed transcript utterances
        3. Windowed messages
        4. Fallback to generic prompt
        """
        parts: list[str] = []

        # User input takes priority as the "subject"
        if self.user_input:
            parts.append(f"Subject: {self.user_input}")

        # Add transcript context if available
        transcript_text = self._get_windowed_transcript()
        if transcript_text:
            parts.append(f"Recent conversation:\n{transcript_text}")

        # Add message context if available (and no transcript)
        if not transcript_text:
            messages_text = self._get_windowed_messages()
            if messages_text:
                parts.append(f"Recent messages:\n{messages_text}")

        if not parts:
            return "random internet humor"

        return "\n\n".join(parts)

    def _get_windowed_transcript(self) -> str:
        """Get transcript utterances within the configured window."""
        if not self.transcript_utterances:
            return ""

        utterances = list(self.transcript_utterances)
        if not utterances:
            return ""

        # Find the cutoff time
        now = utterances[-1].start_time  # Use latest utterance as reference
        cutoff = now - timedelta(minutes=self.max_transcript_minutes)

        # Apply time window
        windowed = [u for u in utterances if u.start_time >= cutoff]

        # Apply count limit (most restrictive)
        if len(windowed) > self.max_transcript_utterances:
            windowed = windowed[-self.max_transcript_utterances :]

        return "\n".join(u.text for u in windowed if u.text.strip())

    def _get_windowed_messages(self) -> str:
        """Get messages within the configured window."""
        if not self.messages:
            return ""

        messages = list(self.messages)
        if not messages:
            return ""

        # Apply count limit
        windowed = messages[-self.max_messages :]

        lines = []
        for msg in windowed:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content.strip():
                lines.append(f"[{role}]: {content}")

        return "\n".join(lines)
