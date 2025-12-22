"""Smoke test for OpenAI providers."""

import asyncio
import os
import wave

from clanker.models import Context, Message, Persona
from clanker.providers.openai_llm import OpenAILLM
from clanker.providers.openai_stt import OpenAISTT


async def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    llm = OpenAILLM(api_key=api_key)
    stt = OpenAISTT(api_key=api_key)

    context = Context(
        request_id="req",
        user_id=1,
        guild_id=None,
        channel_id=2,
        persona=Persona(id="p", display_name="p", system_prompt="You are helpful."),
        messages=[Message(role="user", content="Say hello.")],
        metadata={},
    )

    reply = await llm.generate(context, context.messages)
    print("LLM:", reply.content)

    with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
        audio_bytes = wf.readframes(wf.getnframes())
    transcript = await stt.transcribe(audio_bytes)
    print("STT:", transcript)


if __name__ == "__main__":
    asyncio.run(main())
