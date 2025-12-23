"""Tests for voice ingest worker."""

import wave
from datetime import datetime, timedelta

import pytest

from clanker_bot.voice_ingest import VoiceIngestWorker
from tests.fakes import FakeSTT


@pytest.mark.asyncio()
async def test_voice_ingest_worker_process_once_returns_transcripts() -> None:
    with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
        pcm_bytes = wf.readframes(wf.getnframes())
        sample_rate = wf.getframerate()
    start_time = datetime(2024, 1, 1, 12, 0, 0)
    worker = VoiceIngestWorker(stt=FakeSTT(transcript="hello"), sample_rate_hz=sample_rate)
    worker.add_pcm(123, pcm_bytes, recorded_at=start_time)
    assert worker.should_process()
    events = await worker.process_once()
    assert events
    assert all(event.text == "hello" for event in events)
    assert all(event.start_time >= start_time for event in events)
    duration_seconds = len(pcm_bytes) / (sample_rate * 2)
    assert all(
        event.end_time <= start_time + timedelta(seconds=duration_seconds)
        for event in events
    )
    assert worker.buffers == {}
    assert worker.buffer_start_times == {}


def test_voice_ingest_worker_should_process_requires_threshold() -> None:
    with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
        pcm_bytes = wf.readframes(wf.getnframes())
        sample_rate = wf.getframerate()
    worker = VoiceIngestWorker(stt=FakeSTT(), sample_rate_hz=sample_rate)
    half_second_bytes = pcm_bytes[: sample_rate * 1 * 2]
    worker.add_pcm(42, half_second_bytes)
    assert not worker.should_process()
