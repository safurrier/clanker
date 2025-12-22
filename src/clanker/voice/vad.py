"""Voice activity detection utilities."""

from __future__ import annotations

import audioop
from dataclasses import dataclass


@dataclass(frozen=True)
class SpeechSegment:
    """Represents a segment of detected speech in milliseconds."""

    start_ms: int
    end_ms: int


def detect_speech_segments(
    pcm_bytes: bytes,
    sample_rate_hz: int,
    frame_ms: int = 30,
    threshold: int = 500,
    padding_ms: int = 300,
) -> list[SpeechSegment]:
    """Detect speech segments using simple energy thresholding."""
    frame_size = int(sample_rate_hz * frame_ms / 1000) * 2
    padding_frames = max(1, padding_ms // frame_ms)
    segments: list[SpeechSegment] = []
    speech_start: int | None = None
    silence_frames = 0

    for index in range(0, len(pcm_bytes), frame_size):
        frame = pcm_bytes[index : index + frame_size]
        if len(frame) < frame_size:
            break
        rms = audioop.rms(frame, 2)
        is_speech = rms >= threshold
        frame_start_ms = int(index / 2 / sample_rate_hz * 1000)
        frame_end_ms = int((index + frame_size) / 2 / sample_rate_hz * 1000)

        if is_speech:
            if speech_start is None:
                speech_start = frame_start_ms
            silence_frames = 0
        else:
            if speech_start is not None:
                silence_frames += 1
                if silence_frames >= padding_frames:
                    segments.append(
                        SpeechSegment(start_ms=speech_start, end_ms=frame_end_ms)
                    )
                    speech_start = None
                    silence_frames = 0

    if speech_start is not None:
        end_ms = int(len(pcm_bytes) / 2 / sample_rate_hz * 1000)
        segments.append(SpeechSegment(start_ms=speech_start, end_ms=end_ms))

    return segments
