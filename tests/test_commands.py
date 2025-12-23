"""Tests for Discord command handlers."""

import pytest

from clanker.models import Persona
from clanker.shitposts.memes import load_meme_templates, sample_meme_template
from clanker_bot import commands
from clanker_bot.commands import (
    BotDependencies,
    handle_chat,
    handle_shitpost,
    handle_speak,
)
from clanker_bot.discord_adapter import VoiceSessionManager
from tests.conftest import FakeInteraction
from tests.fakes import FakeImage, FakeLLM, FakeTTS


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
    assert fake_interaction.response.messages == ["Reply posted in thread."]
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
    assert fake_interaction.response.messages == ["Reply posted in thread."]
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
    await handle_shitpost(fake_interaction, "topic", "quip", deps)
    assert fake_interaction.response.messages == ["joke"]


@pytest.mark.asyncio()
async def test_handle_shitpost_meme(
    fake_interaction: FakeInteraction, monkeypatch: pytest.MonkeyPatch
) -> None:
    meme_template = sample_meme_template(
        load_meme_templates(), template_id="aag"
    )
    monkeypatch.setattr(
        commands, "sample_meme_template", lambda _templates: meme_template
    )
    deps = BotDependencies(
        llm=FakeLLM(reply_text='["top", "bottom"]'),
        stt=None,
        tts=None,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        voice_manager=VoiceSessionManager(),
        image=FakeImage(image_bytes=b"meme"),
    )
    await handle_shitpost(fake_interaction, "topic", "meme", deps)
    assert fake_interaction.response.messages == ["top | bottom"]
