"""Tests for voice worker."""

from datetime import datetime, timedelta
import wave

import pytest

from clanker.voice.vad import SpeechSegment
from clanker.voice.worker import AudioBuffer, transcript_loop_once
from tests.fakes import FakeSTT


class FakeDetector:
    def __init__(self, segments: list[SpeechSegment]) -> None:
        self._segments = segments

    def detect(self, pcm_bytes: bytes, sample_rate_hz: int) -> list[SpeechSegment]:
        return self._segments


def _pcm_bytes(duration_ms: int, sample_rate: int) -> bytes:
    total_samples = int(sample_rate * duration_ms / 1000)
    return b"\x00\x00" * total_samples


@pytest.mark.asyncio()
async def test_transcript_loop_once() -> None:
    with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
        pcm_bytes = wf.readframes(wf.getnframes())
        sample_rate = wf.getframerate()
    start_time = datetime(2024, 1, 1, 12, 0, 0)
    detector = FakeDetector([SpeechSegment(start_ms=0, end_ms=2000)])
    buffers = {123: AudioBuffer(pcm_bytes=pcm_bytes, start_time=start_time)}
    events = await transcript_loop_once(
        buffers, FakeSTT(transcript="hello"), sample_rate, detector=detector
    )
    assert events
    assert events[0].speaker_id == 123
    assert events[0].text == "hello"
    assert events[0].start_time >= start_time
    assert events[0].end_time >= events[0].start_time
    duration_seconds = len(pcm_bytes) / (sample_rate * 2)
    assert events[0].end_time <= start_time + timedelta(seconds=duration_seconds)


@pytest.mark.asyncio()
async def test_transcript_loop_once_groups_utterances_by_silence() -> None:
    sample_rate = 16000
    pcm_bytes = _pcm_bytes(2000, sample_rate)
    start_time = datetime(2024, 1, 1, 12, 0, 0)
    detector = FakeDetector(
        [
            SpeechSegment(start_ms=0, end_ms=400),
            SpeechSegment(start_ms=800, end_ms=1200),
        ]
    )
    buffers = {1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=start_time)}
    events = await transcript_loop_once(
        buffers,
        FakeSTT(transcript="hello"),
        sample_rate,
        detector=detector,
        max_silence_ms=200,
        min_utterance_ms=0,  # Disable min duration filter for this test
    )
    assert len(events) == 2
    assert events[0].start_time == start_time
    assert events[1].start_time == start_time + timedelta(milliseconds=800)


@pytest.mark.asyncio()
async def test_transcript_loop_once_orders_events_across_speakers() -> None:
    sample_rate = 16000
    pcm_bytes = _pcm_bytes(1500, sample_rate)
    base = datetime(2024, 1, 1, 12, 0, 0)
    detector = FakeDetector([SpeechSegment(start_ms=0, end_ms=400)])
    buffers = {
        1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=base),
        2: AudioBuffer(pcm_bytes=pcm_bytes, start_time=base + timedelta(seconds=1)),
    }
    events = await transcript_loop_once(
        buffers,
        FakeSTT(transcript="hello"),
        sample_rate,
        detector=detector,
        min_utterance_ms=0,  # Disable min duration filter for this test
    )
    assert [event.speaker_id for event in events] == [1, 2]


@pytest.mark.asyncio()
async def test_transcript_loop_once_filters_short_utterances() -> None:
    """Short utterances below min_utterance_ms are filtered to avoid STT hallucinations."""
    sample_rate = 16000
    pcm_bytes = _pcm_bytes(3000, sample_rate)
    start_time = datetime(2024, 1, 1, 12, 0, 0)
    # Three segments: 400ms (too short), 600ms (long enough), 300ms (too short)
    detector = FakeDetector(
        [
            SpeechSegment(start_ms=0, end_ms=400),     # 400ms - below 500ms default
            SpeechSegment(start_ms=1000, end_ms=1600),  # 600ms - above 500ms default
            SpeechSegment(start_ms=2000, end_ms=2300),  # 300ms - below 500ms default
        ]
    )
    buffers = {1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=start_time)}

    # With default min_utterance_ms=500, only the 600ms segment should pass
    events = await transcript_loop_once(
        buffers,
        FakeSTT(transcript="hello"),
        sample_rate,
        detector=detector,
        max_silence_ms=200,  # Force each segment to be its own utterance
    )
    assert len(events) == 1
    assert events[0].chunk.start_ms == 1000
    assert events[0].chunk.end_ms == 1600

    # With min_utterance_ms=0, all segments should pass
    events_no_filter = await transcript_loop_once(
        buffers,
        FakeSTT(transcript="hello"),
        sample_rate,
        detector=detector,
        max_silence_ms=200,
        min_utterance_ms=0,
    )
    assert len(events_no_filter) == 3
