"""Network smoke tests for the Anthropic LLM provider."""

from __future__ import annotations

import os
import time

import pytest

from clanker.models import Context, Message, Persona
from clanker.providers.anthropic import AnthropicLLM
from clanker.providers.errors import TransientProviderError


@pytest.mark.network()
@pytest.mark.asyncio()
async def test_anthropic_llm_smoke_generates_text() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    llm = AnthropicLLM(api_key=api_key)
    context = Context(
        request_id="smoke-req",
        user_id=1,
        guild_id=None,
        channel_id=2,
        persona=Persona(id="p", display_name="Bot", system_prompt="You are helpful."),
        messages=[Message(role="user", content="Say hello in one sentence.")],
        metadata={},
    )

    reply = await _retry_llm(llm, context)
    assert reply.role == "assistant"
    assert reply.content.strip()


async def _retry_llm(llm: AnthropicLLM, context: Context) -> Message:
    for attempt in range(2):
        try:
            return await llm.generate(
                context,
                list(context.messages),
                params={"max_tokens": 30},
            )
        except TransientProviderError:
            if attempt == 1:
                raise
            time.sleep(1)
    raise AssertionError("Retry did not return")
