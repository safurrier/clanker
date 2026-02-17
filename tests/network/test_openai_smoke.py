"""Network smoke tests for OpenAI providers."""

from __future__ import annotations

import os
import time
import wave

import pytest

from clanker.models import Context, Message, Persona
from clanker.providers.errors import TransientProviderError
from clanker.providers.openai import OpenAILLM, OpenAISTT


@pytest.mark.network()
@pytest.mark.asyncio()
async def test_openai_llm_smoke_generates_text() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    llm = OpenAILLM(api_key=api_key)
    context = Context(
        request_id="req",
        user_id=1,
        guild_id=None,
        channel_id=2,
        persona=Persona(id="p", display_name="p", system_prompt="You are helpful."),
        messages=[Message(role="user", content="Say hello in one sentence.")],
        metadata={},
    )

    reply = await _retry_llm(llm, context)
    assert reply.content.strip()


async def _retry_llm(llm: OpenAILLM, context: Context) -> Message:
    for attempt in range(2):
        try:
            return await llm.generate(
                context,
                context.messages,
                params={"max_tokens": 20, "temperature": 0},
            )
        except TransientProviderError:
            if attempt == 1:
                raise
            time.sleep(1)
    raise AssertionError("Retry did not return")


@pytest.mark.network()
@pytest.mark.asyncio()
async def test_openai_stt_smoke_transcribes_fixture() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    stt = OpenAISTT(api_key=api_key)
    # Read the complete WAV file with headers, not just the PCM frames
    with open("tests/audio_fixtures/test_tone.wav", "rb") as f:
        audio_bytes = f.read()

    transcript = await _retry_stt(stt, audio_bytes)
    assert transcript.strip()


async def _retry_stt(stt: OpenAISTT, audio_bytes: bytes) -> str:
    for attempt in range(2):
        try:
            return await stt.transcribe(audio_bytes)
        except TransientProviderError:
            if attempt == 1:
                raise
            time.sleep(1)
    raise AssertionError("Retry did not return")
