"""Tests for voice ingest worker and sink."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import wave

import pytest

from clanker.voice.vad import SpeechSegment
from clanker_bot.voice_ingest import VoiceIngestSink, VoiceIngestWorker
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
        chunk_seconds=2.0,  # Use shorter threshold for test
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
        stt=FakeSTT(),
        sample_rate_hz=sample_rate,
        chunk_seconds=2.0,  # Use shorter threshold for test
        detector=detector,
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
        chunk_seconds=2.0,  # Use shorter threshold for test
        detector=detector,
    )
    worker.add_pcm(1, pcm_bytes, recorded_at=datetime(2024, 1, 1, 12, 0, 0))
    worker.add_pcm(2, pcm_bytes, recorded_at=datetime(2024, 1, 1, 12, 0, 1))
    events = await worker.process_once()
    assert [event.speaker_id for event in events] == [1, 2]


# --- VoiceIngestSink Tests ---


class TestVoiceIngestSink:
    """Test VoiceIngestSink abstract method implementations."""

    @pytest.fixture
    def worker(self) -> VoiceIngestWorker:
        """Create a VoiceIngestWorker with fake STT."""
        return VoiceIngestWorker(stt=FakeSTT())

    @pytest.fixture
    def sink(self, worker: VoiceIngestWorker) -> VoiceIngestSink:
        """Create a VoiceIngestSink for testing."""
        return VoiceIngestSink(worker)

    def test_sink_can_be_instantiated(self, worker: VoiceIngestWorker) -> None:
        """Sink should be instantiable (not abstract)."""
        sink = VoiceIngestSink(worker)
        assert sink is not None

    def test_wants_opus_returns_false(self, sink: VoiceIngestSink) -> None:
        """Sink should request PCM, not Opus-encoded audio."""
        assert sink.wants_opus() is False

    @pytest.mark.asyncio
    async def test_cleanup_cancels_pending_tasks(
        self, sink: VoiceIngestSink
    ) -> None:
        """Cleanup should cancel all pending processing tasks."""
        # Arrange: add some fake tasks
        task1 = asyncio.create_task(asyncio.sleep(100))
        task2 = asyncio.create_task(asyncio.sleep(100))
        sink._tasks.add(task1)
        sink._tasks.add(task2)

        # Act
        sink.cleanup()

        # Assert: tasks set is cleared
        assert len(sink._tasks) == 0

        # Assert: tasks are in cancelling state
        # (cancel() schedules cancellation, cancelled() is True after CancelledError is raised)
        assert task1.cancelling() > 0
        assert task2.cancelling() > 0

    def test_cleanup_handles_empty_tasks(self, sink: VoiceIngestSink) -> None:
        """Cleanup should handle case with no pending tasks."""
        sink.cleanup()  # Should not raise
        assert len(sink._tasks) == 0
