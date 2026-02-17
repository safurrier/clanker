"""Tests for voice chunking."""

import wave

from clanker.voice.chunker import chunk_segments
from clanker.voice.vad import detect_speech_segments


def test_detect_speech_segments() -> None:
    with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
        pcm_bytes = wf.readframes(wf.getnframes())
        sample_rate = wf.getframerate()
    segments = detect_speech_segments(pcm_bytes, sample_rate)
    assert segments


def test_chunk_segments_overlap() -> None:
    segments = [
        type("Segment", (), {"start_ms": 0, "end_ms": 8000})(),
    ]
    chunks = chunk_segments(segments, min_seconds=2.0, max_seconds=3.0, overlap_ms=200)
    assert len(chunks) >= 3
    assert chunks[1].start_ms < chunks[0].end_ms
