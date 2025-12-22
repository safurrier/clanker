"""Tests for voice worker."""

import wave

import pytest

from clanker.voice.worker import transcript_loop_once
from tests.fakes import FakeSTT


@pytest.mark.asyncio()
async def test_transcript_loop_once() -> None:
    with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
        pcm_bytes = wf.readframes(wf.getnframes())
        sample_rate = wf.getframerate()
    buffers = {123: pcm_bytes}
    events = await transcript_loop_once(
        buffers, FakeSTT(transcript="hello"), sample_rate
    )
    assert events
    assert events[0].speaker_id == 123
    assert events[0].text == "hello"
