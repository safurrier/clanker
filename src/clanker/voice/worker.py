"""Voice transcript worker utilities."""

from __future__ import annotations

import struct
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..models import Context, Message
from ..providers.base import STT
from .chunker import AudioChunk, chunk_segments
from .vad import detect_speech_segments


@dataclass(frozen=True)
class TranscriptEvent:
    """Transcript event emitted by the voice worker."""

    speaker_id: int
    chunk_id: str
    text: str
    chunk: AudioChunk
    start_time: datetime
    end_time: datetime


@dataclass(frozen=True)
class AudioBuffer:
    """PCM buffer with a start timestamp."""

    pcm_bytes: bytes
    start_time: datetime


async def transcript_loop_once(
    buffers: Mapping[int, AudioBuffer],
    stt: STT,
    sample_rate_hz: int,
) -> list[TranscriptEvent]:
    """Process per-user audio buffers once and return transcript events."""
    events: list[TranscriptEvent] = []
    for speaker_id, buffer in buffers.items():
        pcm_bytes = buffer.pcm_bytes
        segments = detect_speech_segments(pcm_bytes, sample_rate_hz)
        chunks = chunk_segments(segments)
        for index, chunk in enumerate(chunks):
            chunk_bytes = _slice_pcm(pcm_bytes, sample_rate_hz, chunk)
            text = await stt.transcribe(chunk_bytes)
            start_time = buffer.start_time + timedelta(milliseconds=chunk.start_ms)
            end_time = buffer.start_time + timedelta(milliseconds=chunk.end_ms)
            events.append(
                TranscriptEvent(
                    speaker_id=speaker_id,
                    chunk_id=f"{speaker_id}-{index}",
                    text=text,
                    chunk=chunk,
                    start_time=start_time,
                    end_time=end_time,
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
    """Slice PCM bytes for a chunk and wrap in WAV container."""
    start_index = int(chunk.start_ms / 1000 * sample_rate_hz) * 2
    end_index = int(chunk.end_ms / 1000 * sample_rate_hz) * 2
    pcm_chunk = pcm_bytes[start_index:end_index]
    return _wrap_pcm_as_wav(pcm_chunk, sample_rate_hz)


def _wrap_pcm_as_wav(pcm_bytes: bytes, sample_rate_hz: int) -> bytes:
    """Wrap raw PCM bytes in a WAV container with proper headers."""
    num_channels = 1  # Mono
    bits_per_sample = 16  # 16-bit PCM
    byte_rate = sample_rate_hz * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm_bytes)
    file_size = 36 + data_size  # WAV header is 44 bytes, file size excludes first 8

    # Build WAV header
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",  # ChunkID
        file_size,  # ChunkSize
        b"WAVE",  # Format
        b"fmt ",  # Subchunk1ID
        16,  # Subchunk1Size (16 for PCM)
        1,  # AudioFormat (1 for PCM)
        num_channels,  # NumChannels
        sample_rate_hz,  # SampleRate
        byte_rate,  # ByteRate
        block_align,  # BlockAlign
        bits_per_sample,  # BitsPerSample
        b"data",  # Subchunk2ID
        data_size,  # Subchunk2Size
    )

    return header + pcm_bytes
