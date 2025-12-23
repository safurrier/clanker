"""Tests for shitpost generation."""

import pytest

from clanker.models import Context, Message, Persona
from clanker.shitposts import (
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
    request = build_request(template, topic="clankers")
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
        topic="aliens",
    )
    assert reply == ["top line", "bottom line"]
