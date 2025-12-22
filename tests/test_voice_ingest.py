"""Tests for voice ingest worker."""

import wave

import pytest

from clanker_bot.voice_ingest import VoiceIngestWorker
from tests.fakes import FakeSTT


@pytest.mark.asyncio()
async def test_voice_ingest_worker_process_once_returns_transcripts() -> None:
    with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
        pcm_bytes = wf.readframes(wf.getnframes())
        sample_rate = wf.getframerate()
    worker = VoiceIngestWorker(stt=FakeSTT(transcript="hello"), sample_rate_hz=sample_rate)
    worker.add_pcm(123, pcm_bytes)
    assert worker.should_process()
    texts = await worker.process_once()
    assert texts
    assert all(text == "hello" for text in texts)
    assert worker.buffers == {}


def test_voice_ingest_worker_should_process_requires_threshold() -> None:
    with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
        pcm_bytes = wf.readframes(wf.getnframes())
        sample_rate = wf.getframerate()
    worker = VoiceIngestWorker(stt=FakeSTT(), sample_rate_hz=sample_rate)
    half_second_bytes = pcm_bytes[: sample_rate * 1 * 2]
    worker.add_pcm(42, half_second_bytes)
    assert not worker.should_process()
