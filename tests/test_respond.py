"""Tests for respond use-case."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from clanker.models import Context, Message, Persona
from clanker.respond import respond
from tests.fakes import FakeLLM, FakeTTS


@pytest.mark.asyncio()
async def test_respond_writes_replay_log(tmp_path: Path) -> None:
    persona = Persona(
        id="test",
        display_name="Test",
        system_prompt="sys",
        tts_voice="voice",
    )
    context = Context(
        request_id="req",
        user_id=1,
        guild_id=None,
        channel_id=2,
        persona=persona,
        messages=[Message(role="user", content="hi")],
        metadata={},
    )
    log_path = tmp_path / "replay.jsonl"
    reply, audio = await respond(
        context,
        FakeLLM(reply_text="reply"),
        tts=FakeTTS(audio_bytes=b"sound"),
        replay_log_path=log_path,
    )
    assert reply.content == "reply"
    assert audio == b"sound"

    for _ in range(50):
        if log_path.exists():
            break
        await asyncio.sleep(0.01)
    entries = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(entries) == 1
    payload = json.loads(entries[0])
    assert payload["context"]["request_id"] == "req"
    assert payload["response"]["content"] == "reply"
