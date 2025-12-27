"""Data models for voice pipeline debug capture."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..vad import SpeechSegment


@dataclass(frozen=True)
class DebugConfig:
    """Pipeline configuration snapshot for a debug session."""

    sample_rate_hz: int
    chunk_seconds: float
    max_silence_ms: int
    min_utterance_ms: int
    vad_type: str  # "silero" | "energy"


@dataclass(frozen=True)
class CapturedUtterance:
    """Single utterance with all debug artifacts.

    Paths are relative to the session directory.
    """

    user_id: int
    index: int

    # Timing
    start_ms: int
    end_ms: int
    duration_ms: int

    # Audio artifacts (relative paths)
    wav_original_path: str  # At original sample rate
    wav_16khz_path: str  # Resampled to 16kHz

    # VAD context
    source_segments: tuple[SpeechSegment, ...]

    # STT results
    stt_model: str
    stt_text: str
    stt_latency_ms: float


@dataclass
class UserCapture:
    """Per-user capture data for a debug session."""

    user_id: int

    # Raw buffer info
    raw_buffer_path: str  # Relative path to PCM file
    raw_buffer_wav_path: str  # Relative path to WAV version
    raw_buffer_bytes: int
    raw_buffer_duration_ms: int

    # VAD output
    vad_segments: list[SpeechSegment] = field(default_factory=list)
    vad_probabilities: list[float] | None = None  # Silero only

    # Processed utterances
    utterances: list[CapturedUtterance] = field(default_factory=list)
    utterances_filtered_count: int = 0  # Skipped due to min_utterance_ms

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "user_id": self.user_id,
            "raw_buffer_path": self.raw_buffer_path,
            "raw_buffer_wav_path": self.raw_buffer_wav_path,
            "raw_buffer_bytes": self.raw_buffer_bytes,
            "raw_buffer_duration_ms": self.raw_buffer_duration_ms,
            "vad_segments": [
                {"start_ms": s.start_ms, "end_ms": s.end_ms} for s in self.vad_segments
            ],
            "vad_probabilities": self.vad_probabilities,
            "utterances": [
                {
                    "index": u.index,
                    "start_ms": u.start_ms,
                    "end_ms": u.end_ms,
                    "duration_ms": u.duration_ms,
                    "wav_original_path": u.wav_original_path,
                    "wav_16khz_path": u.wav_16khz_path,
                    "source_segments": [
                        {"start_ms": s.start_ms, "end_ms": s.end_ms}
                        for s in u.source_segments
                    ],
                    "stt_model": u.stt_model,
                    "stt_text": u.stt_text,
                    "stt_latency_ms": u.stt_latency_ms,
                }
                for u in self.utterances
            ],
            "utterances_filtered_count": self.utterances_filtered_count,
        }


@dataclass
class DebugSession:
    """Complete debug capture for one processing cycle."""

    session_id: str
    started_at: datetime
    ended_at: datetime | None = None

    # Pipeline config
    config: DebugConfig | None = None

    # Per-user captures
    users: dict[int, UserCapture] = field(default_factory=dict)

    # Aggregate stats (computed at end)
    total_raw_audio_ms: int = 0
    total_speech_detected_ms: int = 0
    total_utterances: int = 0
    total_utterances_filtered: int = 0

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict for manifest."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "config": (
                {
                    "sample_rate_hz": self.config.sample_rate_hz,
                    "chunk_seconds": self.config.chunk_seconds,
                    "max_silence_ms": self.config.max_silence_ms,
                    "min_utterance_ms": self.config.min_utterance_ms,
                    "vad_type": self.config.vad_type,
                }
                if self.config
                else None
            ),
            "users": {str(uid): uc.to_dict() for uid, uc in self.users.items()},
            "stats": {
                "total_raw_audio_ms": self.total_raw_audio_ms,
                "total_speech_detected_ms": self.total_speech_detected_ms,
                "total_utterances": self.total_utterances,
                "total_utterances_filtered": self.total_utterances_filtered,
            },
        }
