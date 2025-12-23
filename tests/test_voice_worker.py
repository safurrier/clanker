"""Tests for voice worker."""

import wave
from datetime import datetime, timedelta

import pytest

from clanker.voice.worker import AudioBuffer, transcript_loop_once
from tests.fakes import FakeSTT


@pytest.mark.asyncio()
async def test_transcript_loop_once() -> None:
    with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
        pcm_bytes = wf.readframes(wf.getnframes())
        sample_rate = wf.getframerate()
    start_time = datetime(2024, 1, 1, 12, 0, 0)
    buffers = {123: AudioBuffer(pcm_bytes=pcm_bytes, start_time=start_time)}
    events = await transcript_loop_once(
        buffers, FakeSTT(transcript="hello"), sample_rate
    )
    assert events
    assert events[0].speaker_id == 123
    assert events[0].text == "hello"
    assert events[0].start_time >= start_time
    assert events[0].end_time >= events[0].start_time
    duration_seconds = len(pcm_bytes) / (sample_rate * 2)
    assert events[0].end_time <= start_time + timedelta(seconds=duration_seconds)
