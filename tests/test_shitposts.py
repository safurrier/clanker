"""Tests for shitpost generation."""

from datetime import datetime, timedelta

import pytest

from clanker.models import Context, Message, Persona
from clanker.shitposts import (
    ShitpostContext,
    build_request,
    load_meme_templates,
    load_templates,
    render_meme_text,
    render_shitpost,
    sample_meme_template,
    sample_template,
)
from tests.fakes import FakeLLM


@pytest.mark.asyncio()
async def test_render_shitpost() -> None:
    templates = load_templates()
    template = sample_template(templates, name="one_liner")
    shitpost_context = ShitpostContext(user_input="clankers")
    request = build_request(template, shitpost_context)
    context = Context(
        request_id="req",
        user_id=1,
        guild_id=None,
        channel_id=2,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        messages=[Message(role="user", content="")],
        metadata={},
    )
    reply = await render_shitpost(context, FakeLLM(reply_text="joke"), request)
    assert reply.content == "joke"


def test_load_meme_templates_filters_disabled() -> None:
    templates = load_meme_templates()
    template_ids = {template.template_id for template in templates}
    assert "aag" in template_ids
    assert "zero-wing" not in template_ids


@pytest.mark.asyncio()
async def test_render_meme_text() -> None:
    templates = load_meme_templates()
    meme = sample_meme_template(templates, template_id="aag")
    shitpost_context = ShitpostContext(user_input="aliens")
    context = Context(
        request_id="req",
        user_id=1,
        guild_id=None,
        channel_id=2,
        persona=Persona(id="p", display_name="p", system_prompt="sys"),
        messages=[Message(role="user", content="")],
        metadata={},
    )
    reply = await render_meme_text(
        context,
        FakeLLM(reply_text='["top line", "bottom line"]'),
        meme,
        shitpost_context,
    )
    assert reply == ["top line", "bottom line"]


# =============================================================================
# ShitpostContext Unit Tests
# =============================================================================


class FakeUtterance:
    """Test utterance for ShitpostContext tests."""

    def __init__(self, text: str, start_time: datetime) -> None:
        self._text = text
        self._start_time = start_time

    @property
    def text(self) -> str:
        return self._text

    @property
    def start_time(self) -> datetime:
        return self._start_time


def test_shitpost_context_user_input_only() -> None:
    """User input should be used as subject."""
    ctx = ShitpostContext(user_input="cats are great")
    result = ctx.get_prompt_input()
    assert "Subject: cats are great" in result


def test_shitpost_context_fallback() -> None:
    """Empty context should return fallback."""
    ctx = ShitpostContext()
    assert ctx.get_prompt_input() == "random internet humor"


def test_shitpost_context_transcript_windowing_by_time() -> None:
    """Transcript should be windowed by time."""
    now = datetime.now()
    utterances = (
        FakeUtterance("old message", now - timedelta(minutes=10)),
        FakeUtterance("recent message 1", now - timedelta(minutes=2)),
        FakeUtterance("recent message 2", now - timedelta(minutes=1)),
        FakeUtterance("latest message", now),
    )
    ctx = ShitpostContext(
        transcript_utterances=utterances,
        max_transcript_minutes=5.0,
    )
    result = ctx.get_prompt_input()
    assert "old message" not in result
    assert "recent message 1" in result
    assert "recent message 2" in result
    assert "latest message" in result


def test_shitpost_context_transcript_windowing_by_count() -> None:
    """Transcript should be windowed by count when more restrictive."""
    now = datetime.now()
    # All within time window, but exceed count limit
    utterances = tuple(
        FakeUtterance(f"message {i}", now - timedelta(seconds=i * 10))
        for i in range(10, 0, -1)
    )
    ctx = ShitpostContext(
        transcript_utterances=utterances,
        max_transcript_minutes=5.0,
        max_transcript_utterances=3,
    )
    result = ctx.get_prompt_input()
    # Should only have last 3 messages
    assert "message 1" in result
    assert "message 2" in result
    assert "message 3" in result
    assert "message 10" not in result


def test_shitpost_context_messages_windowing() -> None:
    """Messages should be windowed by count."""
    messages = tuple({"role": "user", "content": f"msg {i}"} for i in range(20))
    ctx = ShitpostContext(
        messages=messages,
        max_messages=5,
    )
    result = ctx.get_prompt_input()
    # Should only have last 5
    assert "msg 15" in result
    assert "msg 19" in result
    assert "msg 0" not in result
    assert "msg 14" not in result


def test_shitpost_context_user_input_with_transcript() -> None:
    """User input and transcript should both appear."""
    now = datetime.now()
    utterances = (FakeUtterance("someone said hello", now),)
    ctx = ShitpostContext(
        user_input="make it funny",
        transcript_utterances=utterances,
    )
    result = ctx.get_prompt_input()
    assert "Subject: make it funny" in result
    assert "someone said hello" in result


def test_shitpost_context_transcript_preferred_over_messages() -> None:
    """Transcript should be used instead of messages when both provided."""
    now = datetime.now()
    utterances = (FakeUtterance("voice chat content", now),)
    messages = ({"role": "user", "content": "text chat content"},)
    ctx = ShitpostContext(
        transcript_utterances=utterances,
        messages=messages,
    )
    result = ctx.get_prompt_input()
    assert "voice chat content" in result
    assert "text chat content" not in result
