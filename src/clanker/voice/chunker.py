"""Audio chunking utilities."""

from __future__ import annotations

from dataclasses import dataclass

from .vad import SpeechSegment


@dataclass(frozen=True)
class AudioChunk:
    """Represents a chunk of audio in milliseconds."""

    start_ms: int
    end_ms: int


def chunk_segments(
    segments: list[SpeechSegment],
    min_seconds: float = 2.0,
    max_seconds: float = 6.0,
    overlap_ms: int = 300,
) -> list[AudioChunk]:
    """Chunk speech segments into bounded audio chunks with overlap."""
    chunks: list[AudioChunk] = []
    min_ms = int(min_seconds * 1000)
    max_ms = int(max_seconds * 1000)

    for segment in segments:
        start = segment.start_ms
        end = segment.end_ms
        current = start
        while current < end:
            chunk_end = min(current + max_ms, end)
            if chunk_end - current < min_ms and chunk_end < end:
                chunk_end = min(current + min_ms, end)
            chunks.append(AudioChunk(start_ms=current, end_ms=chunk_end))
            if chunk_end == end:
                break
            current = max(chunk_end - overlap_ms, current + min_ms)

    return chunks
