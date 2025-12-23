"""Tests for voice ingest worker."""

from datetime import datetime, timedelta
import wave

import pytest

from clanker.voice.vad import SpeechSegment
from clanker_bot.voice_ingest import VoiceIngestWorker
from tests.fakes import FakeSTT


class FakeDetector:
    def __init__(self, segments: list[SpeechSegment]) -> None:
        self._segments = segments

    def detect(self, pcm_bytes: bytes, sample_rate_hz: int) -> list[SpeechSegment]:
        return self._segments


@pytest.mark.asyncio()
async def test_voice_ingest_worker_process_once_returns_transcripts() -> None:
    with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
        pcm_bytes = wf.readframes(wf.getnframes())
        sample_rate = wf.getframerate()
    start_time = datetime(2024, 1, 1, 12, 0, 0)
    detector = FakeDetector([SpeechSegment(start_ms=0, end_ms=2000)])
    worker = VoiceIngestWorker(
        stt=FakeSTT(transcript="hello"),
        sample_rate_hz=sample_rate,
        detector=detector,
    )
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
    detector = FakeDetector([SpeechSegment(start_ms=0, end_ms=2000)])
    worker = VoiceIngestWorker(
        stt=FakeSTT(), sample_rate_hz=sample_rate, detector=detector
    )
    half_second_bytes = pcm_bytes[: sample_rate * 1 * 2]
    worker.add_pcm(42, half_second_bytes)
    assert not worker.should_process()


@pytest.mark.asyncio()
async def test_voice_ingest_worker_orders_events_across_speakers() -> None:
    sample_rate = 16000
    pcm_bytes = b"\x00\x00" * sample_rate
    detector = FakeDetector([SpeechSegment(start_ms=0, end_ms=500)])
    worker = VoiceIngestWorker(
        stt=FakeSTT(transcript="hello"),
        sample_rate_hz=sample_rate,
        detector=detector,
    )
    worker.add_pcm(1, pcm_bytes, recorded_at=datetime(2024, 1, 1, 12, 0, 0))
    worker.add_pcm(2, pcm_bytes, recorded_at=datetime(2024, 1, 1, 12, 0, 1))
    events = await worker.process_once()
    assert [event.speaker_id for event in events] == [1, 2]
