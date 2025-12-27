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


class TestIdleFlush:
    """Tests for idle flush mechanism."""

    def test_should_process_true_when_idle_timeout_reached(self) -> None:
        """should_process returns True when buffer has data and idle timeout reached."""
        sample_rate = 16000
        worker = VoiceIngestWorker(
            stt=FakeSTT(),
            sample_rate_hz=sample_rate,
            chunk_seconds=10.0,  # High threshold - won't hit this
            idle_timeout_seconds=3.0,
        )
        # Add small amount of data (won't hit chunk threshold)
        small_pcm = b"\x00\x00" * (sample_rate * 1)  # 1 second
        worker.add_pcm(42, small_pcm)

        # Shouldn't process yet - not enough data and not idle
        assert not worker.should_process()

        # Simulate time passing by backdating _last_audio_time
        worker._last_audio_time = datetime.now() - timedelta(seconds=4.0)

        # Now should process due to idle timeout
        assert worker.should_process()

    def test_should_process_false_when_idle_but_no_data(self) -> None:
        """should_process returns False when idle but no buffered data."""
        worker = VoiceIngestWorker(
            stt=FakeSTT(),
            sample_rate_hz=16000,
            chunk_seconds=10.0,
            idle_timeout_seconds=3.0,
        )
        # No data added, just set last audio time in the past
        worker._last_audio_time = datetime.now() - timedelta(seconds=10.0)

        # Shouldn't process - no data even though "idle"
        assert not worker.should_process()

    def test_should_process_false_when_data_but_not_idle_enough(self) -> None:
        """should_process returns False when has data but not idle long enough."""
        sample_rate = 16000
        worker = VoiceIngestWorker(
            stt=FakeSTT(),
            sample_rate_hz=sample_rate,
            chunk_seconds=10.0,  # High threshold
            idle_timeout_seconds=3.0,
        )
        # Add small amount of data
        small_pcm = b"\x00\x00" * (sample_rate * 1)  # 1 second
        worker.add_pcm(42, small_pcm)

        # Only 1 second idle (less than 3s timeout)
        worker._last_audio_time = datetime.now() - timedelta(seconds=1.0)

        # Shouldn't process - not enough data AND not idle enough
        assert not worker.should_process()

    def test_chunk_threshold_still_works_with_idle_flush(self) -> None:
        """Chunk threshold should still trigger processing even if not idle."""
        sample_rate = 16000
        worker = VoiceIngestWorker(
            stt=FakeSTT(),
            sample_rate_hz=sample_rate,
            chunk_seconds=2.0,  # Low threshold
            idle_timeout_seconds=10.0,  # High idle timeout - won't hit this
        )
        # Add enough data to hit chunk threshold (2+ seconds)
        large_pcm = b"\x00\x00" * (sample_rate * 3)  # 3 seconds
        worker.add_pcm(42, large_pcm)

        # Should process due to chunk threshold (even though not idle)
        assert worker.should_process()

    def test_add_pcm_updates_last_audio_time(self) -> None:
        """add_pcm should update _last_audio_time."""
        worker = VoiceIngestWorker(
            stt=FakeSTT(),
            sample_rate_hz=16000,
            chunk_seconds=10.0,
            idle_timeout_seconds=3.0,
        )
        assert worker._last_audio_time is None

        worker.add_pcm(42, b"\x00\x00" * 100)

        assert worker._last_audio_time is not None
        assert (datetime.now() - worker._last_audio_time).total_seconds() < 1.0

    @pytest.mark.asyncio
    async def test_idle_flush_processes_partial_buffer(self) -> None:
        """Idle flush should process partial buffers that don't hit threshold."""
        sample_rate = 16000
        detector = FakeDetector([SpeechSegment(start_ms=0, end_ms=500)])
        worker = VoiceIngestWorker(
            stt=FakeSTT(transcript="partial"),
            sample_rate_hz=sample_rate,
            chunk_seconds=10.0,  # High threshold - won't hit
            idle_timeout_seconds=3.0,
            detector=detector,
        )
        # Add 1 second of audio (less than 10s threshold)
        pcm_bytes = b"\x00\x00" * sample_rate
        worker.add_pcm(123, pcm_bytes, recorded_at=datetime(2024, 1, 1, 12, 0, 0))

        # Simulate idle timeout
        worker._last_audio_time = datetime.now() - timedelta(seconds=4.0)

        # Should be able to process now
        assert worker.should_process()
        events = await worker.process_once()

        # Should have processed the partial buffer
        assert len(events) == 1
        assert events[0].text == "partial"


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
    async def test_cleanup_cancels_processing_task(
        self, sink: VoiceIngestSink
    ) -> None:
        """Cleanup should cancel the background processing task."""
        # Arrange: start the processing task
        sink.start_processing()
        assert sink._process_task is not None
        task = sink._process_task

        # Act
        sink.cleanup()

        # Assert: task is cleared and cancelled
        assert sink._process_task is None
        assert task.cancelled() or task.cancelling() > 0

    def test_cleanup_handles_no_processing_task(self, sink: VoiceIngestSink) -> None:
        """Cleanup should handle case when processing not started."""
        assert sink._process_task is None
        sink.cleanup()  # Should not raise
        assert sink._process_task is None
