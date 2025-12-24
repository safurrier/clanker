"""E2E behavioral tests for audio capture scenarios.

Tests realistic audio scenarios like long monologues, overlapping speakers,
silence handling, and multi-speaker conversations.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from clanker.voice.vad import EnergyVAD, SpeechSegment
from clanker.voice.worker import AudioBuffer, transcript_loop_once
from clanker_bot.voice_ingest import VoiceIngestWorker
from tests.fakes import FakeSTT


class FakeDetector:
    """Deterministic speech detector for testing."""

    def __init__(self, segments: list[SpeechSegment]) -> None:
        self._segments = segments

    def detect(self, pcm_bytes: bytes, sample_rate_hz: int) -> list[SpeechSegment]:
        return self._segments


def _generate_pcm(duration_ms: int, sample_rate: int = 16000) -> bytes:
    """Generate silent PCM audio for testing."""
    total_samples = int(sample_rate * duration_ms / 1000)
    return b"\x00\x00" * total_samples


@pytest.mark.asyncio()
async def test_long_monologue_produces_multiple_utterances() -> None:
    """Test: Long monologue is split into multiple utterances based on pauses.

    Scenario: Speaker talks for 10 seconds with 2 natural pauses (>500ms).
    Expected: 3 separate transcript events (one per utterance).
    """
    sample_rate = 16000
    pcm_bytes = _generate_pcm(10000, sample_rate)  # 10 seconds

    # Simulate speech with pauses: [0-2s] pause [3-5s] pause [7-9s]
    detector = FakeDetector(
        [
            SpeechSegment(start_ms=0, end_ms=2000),  # Utterance 1
            SpeechSegment(start_ms=3000, end_ms=5000),  # Utterance 2
            SpeechSegment(start_ms=7000, end_ms=9000),  # Utterance 3
        ]
    )

    start_time = datetime(2024, 1, 1, 12, 0, 0)
    buffers = {1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=start_time)}

    events = await transcript_loop_once(
        buffers,
        FakeSTT(transcript="part"),
        sample_rate,
        detector=detector,
        max_silence_ms=500,
    )

    # Verify: 3 utterances from single speaker
    assert len(events) == 3
    assert all(event.speaker_id == 1 for event in events)

    # Verify: Events are chronologically ordered
    assert events[0].start_time == start_time
    assert events[1].start_time == start_time + timedelta(seconds=3)
    assert events[2].start_time == start_time + timedelta(seconds=7)

    # Verify: Each event has correct duration
    assert events[0].end_time - events[0].start_time == timedelta(seconds=2)
    assert events[1].end_time - events[1].start_time == timedelta(seconds=2)
    assert events[2].end_time - events[2].start_time == timedelta(seconds=2)


@pytest.mark.asyncio()
async def test_overlapping_speakers_sorted_chronologically() -> None:
    """Test: Multiple speakers with overlapping speech are sorted by start time.

    Scenario: 3 speakers start at different times (A at :00, B at :01, C at :02).
    Expected: Events ordered by actual start time (A, B, C).
    """
    sample_rate = 16000
    pcm_bytes = _generate_pcm(5000, sample_rate)

    detector = FakeDetector([SpeechSegment(start_ms=0, end_ms=2000)])

    # Speaker 1 starts at 12:00:00
    # Speaker 2 starts at 12:00:01 (1 second later)
    # Speaker 3 starts at 12:00:02 (2 seconds later)
    buffers = {
        1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime(2024, 1, 1, 12, 0, 0)),
        2: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime(2024, 1, 1, 12, 0, 1)),
        3: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime(2024, 1, 1, 12, 0, 2)),
    }

    events = await transcript_loop_once(
        buffers, FakeSTT(transcript="speech"), sample_rate, detector=detector
    )

    # Verify: 3 events sorted by start time
    assert len(events) == 3
    assert events[0].speaker_id == 1  # Speaks first
    assert events[1].speaker_id == 2  # Speaks second
    assert events[2].speaker_id == 3  # Speaks third


@pytest.mark.asyncio()
async def test_rapid_back_and_forth_conversation() -> None:
    """Test: Rapid conversation between speakers maintains correct ordering.

    Scenario: Two speakers alternate quickly (< 1 second turns).
    Expected: All events in correct chronological order.
    """
    sample_rate = 16000
    pcm_short = _generate_pcm(800, sample_rate)  # 800ms utterances

    detector = FakeDetector([SpeechSegment(start_ms=0, end_ms=800)])

    base_time = datetime(2024, 1, 1, 12, 0, 0)

    # A, B, A, B, A (alternating every 1 second)
    buffers = {
        1: AudioBuffer(pcm_bytes=pcm_short, start_time=base_time),
        2: AudioBuffer(pcm_bytes=pcm_short, start_time=base_time + timedelta(seconds=1)),
        3: AudioBuffer(
            pcm_bytes=pcm_short, start_time=base_time + timedelta(seconds=2)
        ),  # Using user_id 3 instead of overwriting 1
        4: AudioBuffer(pcm_bytes=pcm_short, start_time=base_time + timedelta(seconds=3)),
        5: AudioBuffer(pcm_bytes=pcm_short, start_time=base_time + timedelta(seconds=4)),
    }

    events = await transcript_loop_once(
        buffers, FakeSTT(transcript="turn"), sample_rate, detector=detector
    )

    # Verify: 5 events in chronological order
    assert len(events) == 5
    assert events[0].start_time == base_time
    assert events[1].start_time == base_time + timedelta(seconds=1)
    assert events[2].start_time == base_time + timedelta(seconds=2)
    assert events[3].start_time == base_time + timedelta(seconds=3)
    assert events[4].start_time == base_time + timedelta(seconds=4)


@pytest.mark.asyncio()
async def test_silence_between_utterances_creates_splits() -> None:
    """Test: Silence exceeding max_silence_ms splits speech into separate utterances.

    Scenario: Speaker has 100ms pause (merge) and 600ms pause (split).
    Expected: 100ms pause merged, 600ms pause creates separate utterance.
    """
    sample_rate = 16000
    pcm_bytes = _generate_pcm(5000, sample_rate)

    # Speech segments: [0-1s] 100ms pause [1.1-2s] 600ms pause [2.6-3s]
    detector = FakeDetector(
        [
            SpeechSegment(start_ms=0, end_ms=1000),
            SpeechSegment(start_ms=1100, end_ms=2000),  # 100ms gap (merge)
            SpeechSegment(start_ms=2600, end_ms=3000),  # 600ms gap (split)
        ]
    )

    buffers = {
        1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime(2024, 1, 1, 12, 0, 0))
    }

    events = await transcript_loop_once(
        buffers,
        FakeSTT(transcript="speech"),
        sample_rate,
        detector=detector,
        max_silence_ms=500,
    )

    # Verify: 2 utterances (first two segments merged, third separate)
    assert len(events) == 2
    assert events[0].chunk.end_ms == 2000  # Merged utterance
    assert events[1].chunk.start_ms == 2600  # Separate utterance after long silence


@pytest.mark.asyncio()
async def test_continuous_speech_without_pauses() -> None:
    """Test: Continuous speech without pauses creates single utterance.

    Scenario: Speaker talks continuously for 5 seconds without pauses.
    Expected: Single transcript event.
    """
    sample_rate = 16000
    pcm_bytes = _generate_pcm(5000, sample_rate)

    # Continuous speech (no pauses)
    detector = FakeDetector([SpeechSegment(start_ms=0, end_ms=5000)])

    buffers = {
        1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime(2024, 1, 1, 12, 0, 0))
    }

    events = await transcript_loop_once(
        buffers, FakeSTT(transcript="continuous"), sample_rate, detector=detector
    )

    # Verify: Single event for continuous speech
    assert len(events) == 1
    assert events[0].chunk.end_ms - events[0].chunk.start_ms == 5000


@pytest.mark.asyncio()
async def test_empty_audio_produces_no_events() -> None:
    """Test: Pure silence (no speech detected) produces no transcript events.

    Scenario: 5 seconds of silence.
    Expected: No events.
    """
    sample_rate = 16000
    pcm_bytes = _generate_pcm(5000, sample_rate)

    # No speech detected
    detector = FakeDetector([])

    buffers = {
        1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime(2024, 1, 1, 12, 0, 0))
    }

    events = await transcript_loop_once(
        buffers, FakeSTT(transcript="should not appear"), sample_rate, detector=detector
    )

    # Verify: No events for silence
    assert len(events) == 0


def test_voice_ingest_worker_accumulates_across_multiple_chunks() -> None:
    """Test: Worker accumulates audio across multiple add_pcm calls.

    Scenario: Add small chunks repeatedly until threshold reached.
    Expected: should_process() returns True when accumulated audio >= threshold.
    """
    sample_rate = 16000
    worker = VoiceIngestWorker(
        stt=FakeSTT(),
        sample_rate_hz=sample_rate,
        chunk_seconds=2.0,  # Process every 2 seconds
        detector=FakeDetector([]),
    )

    # Add 1 second of audio (below threshold)
    chunk_1s = _generate_pcm(1000, sample_rate)
    worker.add_pcm(1, chunk_1s)
    assert not worker.should_process()  # Not enough yet

    # Add another 1.5 seconds (total: 2.5s, above threshold)
    chunk_1_5s = _generate_pcm(1500, sample_rate)
    worker.add_pcm(1, chunk_1_5s)
    assert worker.should_process()  # Now ready


@pytest.mark.asyncio()
async def test_voice_ingest_worker_tracks_start_time_per_speaker() -> None:
    """Test: Worker correctly tracks start time for each speaker's buffer.

    Scenario: Add audio from two speakers at different times.
    Expected: Events have correct start times matching first add_pcm call.
    """
    sample_rate = 16000
    pcm_bytes = _generate_pcm(2000, sample_rate)

    detector = FakeDetector([SpeechSegment(start_ms=0, end_ms=1000)])
    worker = VoiceIngestWorker(
        stt=FakeSTT(transcript="test"),
        sample_rate_hz=sample_rate,
        detector=detector,
    )

    time_a = datetime(2024, 1, 1, 12, 0, 0)
    time_b = datetime(2024, 1, 1, 12, 0, 5)

    worker.add_pcm(1, pcm_bytes, recorded_at=time_a)
    worker.add_pcm(2, pcm_bytes, recorded_at=time_b)

    events = await worker.process_once()

    # Verify: Each speaker's event has their original start time
    speaker_1_event = next(e for e in events if e.speaker_id == 1)
    speaker_2_event = next(e for e in events if e.speaker_id == 2)

    assert speaker_1_event.start_time == time_a
    assert speaker_2_event.start_time == time_b


def test_energy_vad_detects_silence_correctly() -> None:
    """Test: EnergyVAD correctly identifies pure silence (no speech).

    Scenario: Silent audio (all zeros).
    Expected: No speech segments detected.
    """
    sample_rate = 16000
    silent_pcm = _generate_pcm(3000, sample_rate)

    detector = EnergyVAD(threshold=500)
    segments = detector.detect(silent_pcm, sample_rate)

    # Verify: No speech in silence
    assert len(segments) == 0


def test_energy_vad_detects_loud_audio() -> None:
    """Test: EnergyVAD detects audio exceeding threshold.

    Scenario: Loud audio (high amplitude).
    Expected: Speech segment detected.
    """
    sample_rate = 16000

    # Generate "loud" audio (alternating max amplitude)
    duration_ms = 1000
    total_samples = int(sample_rate * duration_ms / 1000)
    loud_pcm = b"".join([b"\xFF\x7F\x00\x80"] * (total_samples // 2))

    detector = EnergyVAD(threshold=500, padding_ms=100)
    segments = detector.detect(loud_pcm, sample_rate)

    # Verify: Speech detected
    assert len(segments) > 0
    assert segments[0].start_ms < 100  # Starts near beginning


@pytest.mark.asyncio()
async def test_multiple_speakers_simultaneous_start() -> None:
    """Test: Multiple speakers starting at exact same time are handled.

    Scenario: 3 speakers all start speaking at t=0.
    Expected: All events created, sorted consistently.
    """
    sample_rate = 16000
    pcm_bytes = _generate_pcm(1000, sample_rate)

    detector = FakeDetector([SpeechSegment(start_ms=0, end_ms=1000)])

    same_time = datetime(2024, 1, 1, 12, 0, 0)
    buffers = {
        1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=same_time),
        2: AudioBuffer(pcm_bytes=pcm_bytes, start_time=same_time),
        3: AudioBuffer(pcm_bytes=pcm_bytes, start_time=same_time),
    }

    events = await transcript_loop_once(
        buffers, FakeSTT(transcript="simultaneous"), sample_rate, detector=detector
    )

    # Verify: All 3 speakers transcribed
    assert len(events) == 3
    assert all(event.start_time == same_time for event in events)

    # Verify: Events are deterministically ordered (by speaker_id)
    speaker_ids = [event.speaker_id for event in events]
    assert speaker_ids == sorted(speaker_ids)


@pytest.mark.asyncio()
async def test_utterance_boundaries_preserve_audio_chunk_references() -> None:
    """Test: Each TranscriptEvent contains correct audio chunk boundaries.

    Scenario: Speech from 500ms-1500ms.
    Expected: Event's chunk.start_ms=500, chunk.end_ms=1500.
    """
    sample_rate = 16000
    pcm_bytes = _generate_pcm(2000, sample_rate)

    detector = FakeDetector([SpeechSegment(start_ms=500, end_ms=1500)])

    buffers = {
        1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime(2024, 1, 1, 12, 0, 0))
    }

    events = await transcript_loop_once(
        buffers, FakeSTT(transcript="test"), sample_rate, detector=detector
    )

    # Verify: Chunk boundaries match speech segment
    assert len(events) == 1
    assert events[0].chunk.start_ms == 500
    assert events[0].chunk.end_ms == 1500


@pytest.mark.asyncio()
async def test_silero_vad_timestamps_match_window_size() -> None:
    """Regression test: Verify Silero VAD timestamps use correct window duration.

    Bug fixed: Timestamps were hardcoded to 100ms steps while windows are 32ms
    (512 samples at 16kHz). This caused 3x timing errors in transcript events.

    This test verifies that segment timestamps align with actual audio positions
    based on the window size, not a hardcoded step.
    """
    pytest.importorskip("torch")
    pytest.importorskip("numpy")

    from clanker.voice.vad import SileroVAD

    # Generate 1 second of silent audio
    sample_rate = 16000
    duration_sec = 1.0
    total_samples = int(sample_rate * duration_sec)
    pcm_bytes = b"\x00\x00" * total_samples

    detector = SileroVAD(warmup=True)
    segments = detector.detect(pcm_bytes, sample_rate)

    # Verify: Window duration is 32ms at 16kHz (512 samples / 16000 Hz * 1000 ms/s)
    expected_window_ms = int((512 / sample_rate) * 1000)  # Should be 32ms
    assert expected_window_ms == 32, "Test assumption: window size is 512 samples"

    # If Silero detects speech (it might not with silent audio), verify timestamps
    # are multiples of the actual window duration, not hardcoded 100ms
    if segments:
        for segment in segments:
            # Timestamps should be aligned to 32ms boundaries, not 100ms
            assert (
                segment.start_ms % expected_window_ms == 0
            ), f"start_ms={segment.start_ms} not aligned to {expected_window_ms}ms"

    # Additional verification: Generate audio with a known pattern
    # Create audio with a short burst of "noise" to trigger Silero detection
    import numpy as np

    # Create 500ms of low amplitude sine wave to simulate speech
    duration_ms = 500
    samples_count = int(sample_rate * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, samples_count)
    # 200 Hz sine wave at moderate amplitude
    audio_signal = (np.sin(2 * np.pi * 200 * t) * 10000).astype(np.int16)
    pcm_with_speech = audio_signal.tobytes()

    segments_with_speech = detector.detect(pcm_with_speech, sample_rate)

    # Verify: All segment boundaries are multiples of 32ms, not 100ms
    for segment in segments_with_speech:
        # start_ms and end_ms should be multiples of window_duration_ms (32ms)
        assert (
            segment.start_ms % expected_window_ms == 0
        ), f"Speech segment start_ms={segment.start_ms} not aligned to {expected_window_ms}ms"
        assert (
            segment.end_ms % expected_window_ms == 0
        ), f"Speech segment end_ms={segment.end_ms} not aligned to {expected_window_ms}ms"

        # Verify timestamps are NOT using old buggy 100ms step
        # (A segment at 100ms would be impossible with 32ms windows)
        if segment.start_ms == 100 or segment.end_ms == 100:
            # This would indicate the bug is still present
            pytest.fail(
                f"Segment uses 100ms timestamp (buggy behavior): {segment}"
            )
