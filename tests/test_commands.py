"""Tests for Discord command handlers."""

from dataclasses import dataclass

import pytest

from clanker.models import Persona
from clanker_bot.commands import (
    BotDependencies,
    ResponseMessage,
    handle_chat,
    handle_join,
    handle_leave,
    handle_shitpost,
    handle_speak,
)
from clanker_bot.discord_adapter import VoiceSessionManager, VoiceStatus
from tests.conftest import FakeInteraction
from tests.fakes import FakeLLM, FakeTTS


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
async def test_handle_shitpost(fake_interaction: FakeInteraction) -> None:
    deps = BotDependencies(
        llm=FakeLLM(reply_text="joke"),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=VoiceSessionManager(),
    )
    await handle_shitpost(fake_interaction, "topic", None, deps)
    assert fake_interaction.response.messages == ["joke"]


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


@pytest.mark.asyncio()
async def test_handle_join_success(fake_interaction: FakeInteraction) -> None:
    channel = object()
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
    )
    await handle_join(fake_interaction, deps)
    assert fake_interaction.response.messages == [ResponseMessage.JOINED_VOICE]


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
