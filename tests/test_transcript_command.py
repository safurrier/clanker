"""Tests for /transcript command handler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from clanker.models import Persona
from clanker.voice.worker import TranscriptEvent
from clanker.voice.chunker import AudioChunk
from clanker_bot.command_handlers.types import BotDependencies
from clanker_bot.voice_ingest import TranscriptBuffer


# --- Test Fixtures ---


@dataclass
class FakeFollowup:
    """Fake followup for testing."""

    sent_messages: list[tuple[str, bool]]

    async def send(self, content: str, *, ephemeral: bool = False) -> None:
        self.sent_messages.append((content, ephemeral))


@dataclass
class FakeInteractionResponse:
    """Fake interaction response."""

    deferred: bool = False
    ephemeral: bool = False

    async def defer(self, *, ephemeral: bool = False) -> None:
        self.deferred = True
        self.ephemeral = ephemeral


@dataclass
class FakeUser:
    """Fake Discord user for testing."""

    id: int = 12345


@dataclass
class FakeInteraction:
    """Fake Discord interaction for testing."""

    guild_id: int | None
    response: FakeInteractionResponse
    followup: FakeFollowup
    user: FakeUser | None = None


def make_transcript_event(
    speaker_id: int,
    text: str,
    start_time: datetime,
) -> TranscriptEvent:
    """Create a TranscriptEvent for testing."""
    return TranscriptEvent(
        speaker_id=speaker_id,
        chunk_id=f"{speaker_id}-0",
        text=text,
        chunk=AudioChunk(start_ms=0, end_ms=1000),
        start_time=start_time,
        end_time=start_time,
    )


@pytest.fixture
def persona() -> Persona:
    """Test persona."""
    return Persona(
        id="test",
        display_name="Test Bot",
        system_prompt="You are a test bot.",
        tts_voice=None,
        providers=None,
    )


@pytest.fixture
def transcript_buffer() -> TranscriptBuffer:
    """Create a transcript buffer for testing."""
    return TranscriptBuffer()


# --- Tests ---


class TestTranscriptCommand:
    """Tests for handle_transcript command."""

    @pytest.mark.asyncio
    async def test_shows_no_transcript_message_when_empty(
        self, persona: Persona, transcript_buffer: TranscriptBuffer
    ) -> None:
        """Should show message when no transcripts available."""
        from clanker_bot.command_handlers.transcript import handle_transcript

        deps = BotDependencies(
            llm=None,  # type: ignore[arg-type]
            stt=None,
            tts=None,
            image=None,
            persona=persona,
            voice_manager=None,  # type: ignore[arg-type]
            metrics=None,
            transcript_buffer=transcript_buffer,
        )
        interaction = FakeInteraction(
            guild_id=123,
            response=FakeInteractionResponse(),
            followup=FakeFollowup(sent_messages=[]),
        )

        await handle_transcript(interaction, deps)  # type: ignore[arg-type]

        assert interaction.response.deferred is True
        assert len(interaction.followup.sent_messages) == 1
        assert "No recent transcripts" in interaction.followup.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_formats_transcript_with_timestamps(
        self, persona: Persona, transcript_buffer: TranscriptBuffer
    ) -> None:
        """Should format transcripts with speaker IDs and timestamps."""
        from clanker_bot.command_handlers.transcript import handle_transcript

        # Add some transcript events (use recent timestamps to avoid pruning)
        now = datetime.now()
        transcript_buffer.add(
            123,
            make_transcript_event(
                speaker_id=1001,
                text="Hello everyone",
                start_time=now,
            ),
        )
        transcript_buffer.add(
            123,
            make_transcript_event(
                speaker_id=1002,
                text="Hi there",
                start_time=now,
            ),
        )

        deps = BotDependencies(
            llm=None,  # type: ignore[arg-type]
            stt=None,
            tts=None,
            image=None,
            persona=persona,
            voice_manager=None,  # type: ignore[arg-type]
            metrics=None,
            transcript_buffer=transcript_buffer,
        )
        interaction = FakeInteraction(
            guild_id=123,
            response=FakeInteractionResponse(),
            followup=FakeFollowup(sent_messages=[]),
        )

        await handle_transcript(interaction, deps)  # type: ignore[arg-type]

        assert len(interaction.followup.sent_messages) == 1
        message = interaction.followup.sent_messages[0][0]
        assert "Hello everyone" in message
        assert "Hi there" in message

    @pytest.mark.asyncio
    async def test_handles_no_guild_id(
        self, persona: Persona, transcript_buffer: TranscriptBuffer
    ) -> None:
        """Should handle DM context gracefully."""
        from clanker_bot.command_handlers.transcript import handle_transcript

        deps = BotDependencies(
            llm=None,  # type: ignore[arg-type]
            stt=None,
            tts=None,
            image=None,
            persona=persona,
            voice_manager=None,  # type: ignore[arg-type]
            metrics=None,
            transcript_buffer=transcript_buffer,
        )
        interaction = FakeInteraction(
            guild_id=None,
            response=FakeInteractionResponse(),
            followup=FakeFollowup(sent_messages=[]),
        )

        await handle_transcript(interaction, deps)  # type: ignore[arg-type]

        assert "only works in a server" in interaction.followup.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_handles_no_transcript_buffer(
        self, persona: Persona
    ) -> None:
        """Should handle missing transcript buffer gracefully."""
        from clanker_bot.command_handlers.transcript import handle_transcript

        deps = BotDependencies(
            llm=None,  # type: ignore[arg-type]
            stt=None,
            tts=None,
            image=None,
            persona=persona,
            voice_manager=None,  # type: ignore[arg-type]
            metrics=None,
            transcript_buffer=None,
        )
        interaction = FakeInteraction(
            guild_id=123,
            response=FakeInteractionResponse(),
            followup=FakeFollowup(sent_messages=[]),
        )

        await handle_transcript(interaction, deps)  # type: ignore[arg-type]

        assert "No recent transcripts" in interaction.followup.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_response_is_ephemeral(
        self, persona: Persona, transcript_buffer: TranscriptBuffer
    ) -> None:
        """Transcript response should be ephemeral."""
        from clanker_bot.command_handlers.transcript import handle_transcript

        deps = BotDependencies(
            llm=None,  # type: ignore[arg-type]
            stt=None,
            tts=None,
            image=None,
            persona=persona,
            voice_manager=None,  # type: ignore[arg-type]
            metrics=None,
            transcript_buffer=transcript_buffer,
        )
        interaction = FakeInteraction(
            guild_id=123,
            response=FakeInteractionResponse(),
            followup=FakeFollowup(sent_messages=[]),
        )

        await handle_transcript(interaction, deps)  # type: ignore[arg-type]

        assert interaction.response.ephemeral is True
        assert interaction.followup.sent_messages[0][1] is True  # ephemeral=True
