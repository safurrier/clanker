"""Tests for shitpost generation."""

import pytest

from clanker.models import Context, Message, Persona
from clanker.shitposts import (
    build_request,
    load_templates,
    render_shitpost,
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
