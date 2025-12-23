"""Tests for admin command handlers."""

import pytest

from clanker.models import Persona
from clanker_bot.admin import AdminState
from clanker_bot.commands import (
    BotDependencies,
    handle_admin_active_meetings,
    handle_admin_allow_new_meetings,
    handle_admin_stop_new_meetings,
)
from clanker_bot.discord_adapter import VoiceSessionManager
from tests.conftest import FakeInteraction, FakeUser
from tests.fakes import FakeLLM


@pytest.mark.asyncio()
async def test_admin_commands_require_auth(fake_interaction: FakeInteraction) -> None:
    deps = BotDependencies(
        llm=FakeLLM(),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=VoiceSessionManager(),
        admin_user_ids={99},
        admin_state=AdminState(),
    )
    await handle_admin_active_meetings(fake_interaction, deps)
    assert fake_interaction.response.messages == ["Not authorized."]


@pytest.mark.asyncio()
async def test_admin_toggle_meetings(fake_interaction: FakeInteraction) -> None:
    fake_interaction.user = FakeUser(id=99)
    deps = BotDependencies(
        llm=FakeLLM(),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=VoiceSessionManager(),
        admin_user_ids={99},
        admin_state=AdminState(),
    )
    await handle_admin_stop_new_meetings(fake_interaction, deps)
    await handle_admin_allow_new_meetings(fake_interaction, deps)
    assert deps.admin_state
    assert deps.admin_state.allow_new_meetings is True
    assert fake_interaction.response.messages == [
        "New meetings disabled.",
        "New meetings enabled.",
    ]


@pytest.mark.asyncio()
async def test_admin_active_meetings_authorized(fake_interaction: FakeInteraction) -> None:
    fake_interaction.user = FakeUser(id=99)
    voice_manager = VoiceSessionManager()
    voice_manager.state.active_channel_id = 1234
    deps = BotDependencies(
        llm=FakeLLM(),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=voice_manager,
        admin_user_ids={99},
        admin_state=AdminState(),
    )
    await handle_admin_active_meetings(fake_interaction, deps)
    assert fake_interaction.response.messages == ["Active voice channel: 1234"]
