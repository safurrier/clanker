"""Tests for Discord command handlers."""

from dataclasses import dataclass
from datetime import datetime

import pytest

from clanker.models import Persona
from clanker.shitposts.memes import load_meme_templates, sample_meme_template
from clanker.voice.chunker import AudioChunk
from clanker.voice.worker import TranscriptEvent
from clanker_bot.command_handlers import (
    BotDependencies,
    ResponseMessage,
    handle_chat,
    handle_join,
    handle_leave,
    handle_shitpost_preview,
    handle_speak,
)
from clanker_bot.command_handlers import chat as chat_module
from clanker_bot.discord_adapter import VoiceSessionManager, VoiceStatus
from clanker_bot.voice_ingest import TranscriptBuffer
from tests.conftest import FakeInteraction
from tests.fakes import FakeImage, FakeLLM, FakeTTS


@dataclass
class FakeVoiceState:
    channel: object | None


@dataclass
class FakeVoiceMember:
    id: int
    voice: FakeVoiceState | None


class FakeVoiceSessionManager:
    def __init__(self, join_ok: bool, status: VoiceStatus) -> None:
        self.join_ok = join_ok
        self.status = status
        self.join_calls: list[object] = []
        self.leave_calls = 0

    async def join(
        self,
        channel: object,
        *,
        voice_client_cls: object | None = None,
    ) -> tuple[bool, VoiceStatus]:
        self.join_calls.append((channel, voice_client_cls))
        return self.join_ok, self.status

    async def leave(self) -> tuple[bool, VoiceStatus]:
        self.leave_calls += 1
        return self.join_ok, self.status

    @property
    def active_channel_id(self) -> int | None:
        return None

    @property
    def voice_client(self) -> None:
        return None


@pytest.mark.asyncio()
async def test_handle_chat(fake_interaction: FakeInteraction) -> None:
    deps = BotDependencies(
        llm=FakeLLM(reply_text="hi"),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=VoiceSessionManager(),
    )
    await handle_chat(fake_interaction, "prompt", deps)
    assert fake_interaction.followup.messages == [ResponseMessage.REPLY_IN_THREAD]
    assert fake_interaction.channel
    assert fake_interaction.channel.thread.messages[0].startswith("thread:")
    assert fake_interaction.channel.thread.messages[-1] == "hi"


@pytest.mark.asyncio()
async def test_handle_speak(fake_interaction: FakeInteraction) -> None:
    deps = BotDependencies(
        llm=FakeLLM(reply_text="hi"),
        stt=None,
        tts=FakeTTS(audio_bytes=b"sound"),
        persona=Persona(id="p", display_name="p", system_prompt="sys", tts_voice="v"),
        voice_manager=VoiceSessionManager(),
    )
    await handle_speak(fake_interaction, "prompt", deps)
    assert fake_interaction.followup.messages == [ResponseMessage.REPLY_IN_THREAD]
    assert fake_interaction.channel
    assert fake_interaction.channel.thread.messages[0].startswith("thread:")
    assert fake_interaction.channel.thread.messages[-1] == "hi"


@pytest.mark.asyncio()
async def test_handle_join_requires_voice_channel(
    fake_interaction: FakeInteraction,
) -> None:
    fake_interaction.user = FakeVoiceMember(id=1, voice=FakeVoiceState(channel=None))
    deps = BotDependencies(
        llm=FakeLLM(),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=FakeVoiceSessionManager(
            join_ok=True,
            status=VoiceStatus.OK,
        ),
    )
    await handle_join(fake_interaction, deps)
    assert fake_interaction.response.messages == [ResponseMessage.JOIN_VOICE_FIRST]


@dataclass
class FakeVoiceChannel:
    """Minimal fake voice channel for testing."""

    id: int = 12345
    name: str = "test-voice"


@pytest.mark.asyncio()
async def test_handle_join_success(fake_interaction: FakeInteraction) -> None:
    channel = FakeVoiceChannel()
    fake_interaction.user = FakeVoiceMember(id=1, voice=FakeVoiceState(channel=channel))
    deps = BotDependencies(
        llm=FakeLLM(),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=FakeVoiceSessionManager(
            join_ok=True,
            status=VoiceStatus.OK,
        ),
        voice_ingest_enabled=False,
    )
    await handle_join(fake_interaction, deps)
    # Uses defer() + followup.send() due to potentially slow transcription setup
    assert fake_interaction.response.deferred is True
    assert len(fake_interaction.followup.sent_followups) == 1
    assert fake_interaction.followup.sent_followups[0].content == ResponseMessage.JOINED_VOICE


@pytest.mark.asyncio()
async def test_handle_leave_not_connected(fake_interaction: FakeInteraction) -> None:
    deps = BotDependencies(
        llm=FakeLLM(),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=FakeVoiceSessionManager(
            join_ok=False,
            status=VoiceStatus.NOT_CONNECTED,
        ),
    )
    await handle_leave(fake_interaction, deps)
    assert fake_interaction.response.messages == [VoiceStatus.NOT_CONNECTED]


@pytest.mark.asyncio()
async def test_handle_shitpost_preview_generates_n_previews(
    fake_interaction: FakeInteraction, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test new shitpost preview handler generates N ephemeral previews."""
    meme_template = sample_meme_template(load_meme_templates(), template_id="aag")
    monkeypatch.setattr(
        chat_module, "sample_meme_template", lambda _templates, **kwargs: meme_template
    )
    deps = BotDependencies(
        llm=FakeLLM(reply_text='["top text", "bottom text"]'),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=VoiceSessionManager(),
        image=FakeImage(image_bytes=b"meme-image"),
    )
    await handle_shitpost_preview(fake_interaction, n=2, guidance=None, deps=deps)

    # Should have sent 2 ephemeral followups
    assert fake_interaction.followup.sent_followups is not None
    assert len(fake_interaction.followup.sent_followups) == 2

    for followup in fake_interaction.followup.sent_followups:
        assert followup.ephemeral is True
        assert followup.embed is not None
        assert followup.view is not None
        assert followup.file is not None  # Image was generated


@pytest.mark.asyncio()
async def test_handle_shitpost_preview_with_guidance(
    fake_interaction: FakeInteraction, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test shitpost preview with user guidance."""
    meme_template = sample_meme_template(load_meme_templates(), template_id="aag")
    monkeypatch.setattr(
        chat_module, "sample_meme_template", lambda _templates, **kwargs: meme_template
    )
    deps = BotDependencies(
        llm=FakeLLM(reply_text='["cat meme", "very funny"]'),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=VoiceSessionManager(),
        image=FakeImage(image_bytes=b"cat-meme"),
    )
    await handle_shitpost_preview(
        fake_interaction, n=1, guidance="make it about cats", deps=deps
    )

    assert fake_interaction.followup.sent_followups is not None
    assert len(fake_interaction.followup.sent_followups) == 1
    assert fake_interaction.followup.sent_followups[0].ephemeral is True


@pytest.mark.asyncio()
async def test_handle_shitpost_preview_clamps_n(
    fake_interaction: FakeInteraction, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that n is clamped to valid bounds (1-5)."""
    meme_template = sample_meme_template(load_meme_templates(), template_id="aag")
    monkeypatch.setattr(
        chat_module, "sample_meme_template", lambda _templates, **kwargs: meme_template
    )
    deps = BotDependencies(
        llm=FakeLLM(reply_text='["text"]'),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=VoiceSessionManager(),
        image=FakeImage(image_bytes=b"img"),
    )

    # Test n=10 gets clamped to 5
    await handle_shitpost_preview(fake_interaction, n=10, guidance=None, deps=deps)
    assert fake_interaction.followup.sent_followups is not None
    assert len(fake_interaction.followup.sent_followups) == 5


@pytest.mark.asyncio()
async def test_handle_shitpost_preview_uses_voice_transcript(
    fake_interaction: FakeInteraction, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that shitpost preview uses voice transcript when available."""
    meme_template = sample_meme_template(load_meme_templates(), template_id="aag")
    monkeypatch.setattr(
        chat_module, "sample_meme_template", lambda _templates, **kwargs: meme_template
    )

    # Create transcript buffer with some events
    transcript_buffer = TranscriptBuffer()
    now = datetime.now()
    transcript_buffer.add(
        999,  # guild_id matches fake_interaction
        TranscriptEvent(
            speaker_id=1,
            chunk_id="chunk-1",
            text="Hello from voice channel",
            chunk=AudioChunk(start_ms=0, end_ms=1000),
            start_time=now,
            end_time=now,
        ),
    )

    deps = BotDependencies(
        llm=FakeLLM(reply_text='["voice meme", "text"]'),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=VoiceSessionManager(),
        image=FakeImage(image_bytes=b"img"),
        transcript_buffer=transcript_buffer,
    )

    await handle_shitpost_preview(fake_interaction, n=1, guidance=None, deps=deps)
    assert fake_interaction.followup.sent_followups is not None
    assert len(fake_interaction.followup.sent_followups) == 1
    assert fake_interaction.followup.sent_followups[0].ephemeral is True
