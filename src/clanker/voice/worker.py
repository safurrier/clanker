"""Voice transcript worker utilities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..models import Context, Message
from ..providers.stt import STT
from .chunker import AudioChunk, chunk_segments
from .vad import detect_speech_segments


@dataclass(frozen=True)
class TranscriptEvent:
    """Transcript event emitted by the voice worker."""

    speaker_id: int
    chunk_id: str
    text: str
    chunk: AudioChunk


async def transcript_loop_once(
    buffers: Mapping[int, bytes],
    stt: STT,
    sample_rate_hz: int,
) -> list[TranscriptEvent]:
    """Process per-user audio buffers once and return transcript events."""
    events: list[TranscriptEvent] = []
    for speaker_id, pcm_bytes in buffers.items():
        segments = detect_speech_segments(pcm_bytes, sample_rate_hz)
        chunks = chunk_segments(segments)
        for index, chunk in enumerate(chunks):
            chunk_bytes = _slice_pcm(pcm_bytes, sample_rate_hz, chunk)
            text = await stt.transcribe(chunk_bytes)
            events.append(
                TranscriptEvent(
                    speaker_id=speaker_id,
                    chunk_id=f"{speaker_id}-{index}",
                    text=text,
                    chunk=chunk,
                )
            )
    return events


def build_context_from_event(
    base_context: Context,
    event: TranscriptEvent,
) -> Context:
    """Build a Context for a transcript event."""
    metadata = dict(base_context.metadata)
    metadata.update(
        {"audio_chunk_id": event.chunk_id, "speaker_id": str(event.speaker_id)}
    )
    return Context(
        request_id=base_context.request_id,
        user_id=base_context.user_id,
        guild_id=base_context.guild_id,
        channel_id=base_context.channel_id,
        persona=base_context.persona,
        messages=[Message(role="user", content=event.text)],
        metadata=metadata,
    )


def _slice_pcm(pcm_bytes: bytes, sample_rate_hz: int, chunk: AudioChunk) -> bytes:
    start_index = int(chunk.start_ms / 1000 * sample_rate_hz) * 2
    end_index = int(chunk.end_ms / 1000 * sample_rate_hz) * 2
    return pcm_bytes[start_index:end_index]
