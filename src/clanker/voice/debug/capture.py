"""Voice pipeline debug capture orchestration."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from loguru import logger

from ...providers.audio_utils import _wrap_pcm_as_wav, resample_wav
from ..vad import SpeechSegment
from .models import CapturedUtterance, DebugConfig, DebugSession, UserCapture


def _generate_session_id() -> str:
    """Generate a unique session ID with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"session_{timestamp}_{short_uuid}"


@dataclass
class DebugCapture:
    """Captures voice pipeline stages for offline analysis.

    Enable via VOICE_DEBUG=1 environment variable.
    Output directory can be set via VOICE_DEBUG_DIR (default: ./voice_debug).

    Usage:
        capture = DebugCapture.from_env()
        if capture.enabled:
            capture.start_session(config)
            capture.capture_raw_buffer(user_id, pcm_bytes, sample_rate)
            # ... pipeline stages ...
            capture.end_session()
    """

    output_dir: Path
    enabled: bool = False
    _session: DebugSession | None = field(default=None, repr=False)
    _session_dir: Path | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> DebugCapture:
        """Create a DebugCapture instance from environment variables."""
        enabled = os.getenv("VOICE_DEBUG", "").lower() in ("1", "true", "yes")
        output_dir = Path(os.getenv("VOICE_DEBUG_DIR", "./voice_debug"))
        return cls(output_dir=output_dir, enabled=enabled)

    def start_session(self, config: DebugConfig) -> None:
        """Start a new debug capture session."""
        if not self.enabled:
            return

        session_id = _generate_session_id()
        self._session = DebugSession(
            session_id=session_id,
            started_at=datetime.now(),
            config=config,
        )
        self._session_dir = self.output_dir / session_id
        self._session_dir.mkdir(parents=True, exist_ok=True)
        (self._session_dir / "users").mkdir(exist_ok=True)

        logger.info("debug_capture.session_started: {}", session_id)

    def capture_raw_buffer(
        self,
        user_id: int,
        pcm_bytes: bytes,
        sample_rate_hz: int,
    ) -> None:
        """Capture raw PCM buffer for a user."""
        if not self.enabled or self._session is None or self._session_dir is None:
            return

        user_dir = self._session_dir / "users" / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        # Save raw PCM
        pcm_path = user_dir / "raw_buffer.pcm"
        pcm_path.write_bytes(pcm_bytes)

        # Save as playable WAV
        wav_bytes = _wrap_pcm_as_wav(pcm_bytes, sample_rate_hz)
        wav_path = user_dir / "raw_buffer.wav"
        wav_path.write_bytes(wav_bytes)

        # Calculate duration
        duration_ms = len(pcm_bytes) // 2 * 1000 // sample_rate_hz

        # Create or update user capture
        self._session.users[user_id] = UserCapture(
            user_id=user_id,
            raw_buffer_path=f"users/{user_id}/raw_buffer.pcm",
            raw_buffer_wav_path=f"users/{user_id}/raw_buffer.wav",
            raw_buffer_bytes=len(pcm_bytes),
            raw_buffer_duration_ms=duration_ms,
        )

        logger.debug(
            "debug_capture.raw_buffer: user={} bytes={} duration_ms={}",
            user_id,
            len(pcm_bytes),
            duration_ms,
        )

    def capture_vad_result(
        self,
        user_id: int,
        segments: list[SpeechSegment],
        probabilities: list[float] | None = None,
    ) -> None:
        """Capture VAD detection results for a user."""
        if not self.enabled or self._session is None or self._session_dir is None:
            return

        user_capture = self._session.users.get(user_id)
        if user_capture is None:
            logger.warning("debug_capture.vad_result: no user capture for {}", user_id)
            return

        user_capture.vad_segments = list(segments)
        user_capture.vad_probabilities = probabilities

        # Save to JSON
        user_dir = self._session_dir / "users" / str(user_id)
        segments_path = user_dir / "vad_segments.json"
        segments_path.write_text(
            json.dumps(
                [{"start_ms": s.start_ms, "end_ms": s.end_ms} for s in segments],
                indent=2,
            )
        )

        if probabilities:
            probs_path = user_dir / "vad_probabilities.json"
            probs_path.write_text(json.dumps(probabilities))

        logger.debug(
            "debug_capture.vad_result: user={} segments={}",
            user_id,
            len(segments),
        )

    def capture_filtered_utterance(
        self,
        user_id: int,
        index: int,
        start_ms: int,
        end_ms: int,
        reason: str,
    ) -> None:
        """Record that an utterance was filtered (e.g., too short)."""
        if not self.enabled or self._session is None:
            return

        user_capture = self._session.users.get(user_id)
        if user_capture:
            user_capture.utterances_filtered_count += 1

        logger.debug(
            "debug_capture.filtered: user={} index={} reason={} duration_ms={}",
            user_id,
            index,
            reason,
            end_ms - start_ms,
        )

    def capture_utterance(
        self,
        user_id: int,
        index: int,
        wav_bytes: bytes,
        sample_rate_hz: int,
        start_ms: int,
        end_ms: int,
        source_segments: list[SpeechSegment],
    ) -> None:
        """Capture pre-STT utterance audio."""
        if not self.enabled or self._session is None or self._session_dir is None:
            return

        user_capture = self._session.users.get(user_id)
        if user_capture is None:
            return

        # Create utterance directory
        utt_dir = self._session_dir / "users" / str(user_id) / "utterances" / str(index)
        utt_dir.mkdir(parents=True, exist_ok=True)

        # Save at original rate
        original_path = utt_dir / f"audio_{sample_rate_hz}hz.wav"
        original_path.write_bytes(wav_bytes)

        # Save resampled to 16kHz for comparison
        if sample_rate_hz != 16000:
            wav_16k = resample_wav(wav_bytes, sample_rate_hz, 16000)
            resampled_path = utt_dir / "audio_16khz.wav"
            resampled_path.write_bytes(wav_16k)
        else:
            resampled_path = original_path

        # Store paths for later completion
        # The CapturedUtterance will be finalized in capture_stt_result
        self._pending_utterances = getattr(self, "_pending_utterances", {})
        self._pending_utterances[(user_id, index)] = {
            "wav_original_path": f"users/{user_id}/utterances/{index}/audio_{sample_rate_hz}hz.wav",
            "wav_16khz_path": f"users/{user_id}/utterances/{index}/audio_16khz.wav",
            "start_ms": start_ms,
            "end_ms": end_ms,
            "source_segments": source_segments,
        }

        logger.debug(
            "debug_capture.utterance: user={} index={} duration_ms={}",
            user_id,
            index,
            end_ms - start_ms,
        )

    def capture_stt_result(
        self,
        user_id: int,
        index: int,
        text: str,
        latency_ms: float,
        model: str = "whisper-1",
    ) -> None:
        """Capture STT result and finalize the utterance capture."""
        if not self.enabled or self._session is None or self._session_dir is None:
            return

        user_capture = self._session.users.get(user_id)
        if user_capture is None:
            return

        # Get pending utterance data
        pending = getattr(self, "_pending_utterances", {}).get((user_id, index))
        if pending is None:
            logger.warning(
                "debug_capture.stt_result: no pending utterance for user={} index={}",
                user_id,
                index,
            )
            return

        # Create final utterance record
        utterance = CapturedUtterance(
            user_id=user_id,
            index=index,
            start_ms=pending["start_ms"],
            end_ms=pending["end_ms"],
            duration_ms=pending["end_ms"] - pending["start_ms"],
            wav_original_path=pending["wav_original_path"],
            wav_16khz_path=pending["wav_16khz_path"],
            source_segments=tuple(pending["source_segments"]),
            stt_model=model,
            stt_text=text,
            stt_latency_ms=latency_ms,
        )
        user_capture.utterances.append(utterance)

        # Save STT result JSON
        utt_dir = self._session_dir / "users" / str(user_id) / "utterances" / str(index)
        result_path = utt_dir / "stt_result.json"
        result_path.write_text(
            json.dumps(
                {
                    "model": model,
                    "text": text,
                    "latency_ms": latency_ms,
                },
                indent=2,
            )
        )

        # Clean up pending
        del self._pending_utterances[(user_id, index)]

        logger.debug(
            "debug_capture.stt_result: user={} index={} text_len={} latency_ms={:.0f}",
            user_id,
            index,
            len(text),
            latency_ms,
        )

    def end_session(self) -> Path | None:
        """End the current session and write the manifest."""
        if not self.enabled or self._session is None or self._session_dir is None:
            return None

        self._session.ended_at = datetime.now()

        # Calculate aggregate stats
        for user_capture in self._session.users.values():
            self._session.total_raw_audio_ms += user_capture.raw_buffer_duration_ms
            self._session.total_speech_detected_ms += sum(
                s.end_ms - s.start_ms for s in user_capture.vad_segments
            )
            self._session.total_utterances += len(user_capture.utterances)
            self._session.total_utterances_filtered += (
                user_capture.utterances_filtered_count
            )

        # Write manifest
        manifest_path = self._session_dir / "manifest.json"
        manifest_path.write_text(json.dumps(self._session.to_dict(), indent=2))

        # Write human-readable transcript
        self._write_transcript()

        logger.info(
            "debug_capture.session_ended: {} utterances={} filtered={}",
            self._session.session_id,
            self._session.total_utterances,
            self._session.total_utterances_filtered,
        )

        session_dir = self._session_dir
        self._session = None
        self._session_dir = None
        return session_dir

    def _write_transcript(self) -> None:
        """Write a human-readable transcript file."""
        if self._session is None or self._session_dir is None:
            return

        lines = [
            f"Voice Debug Session: {self._session.session_id}",
            f"Started: {self._session.started_at.isoformat()}",
            f"Ended: {self._session.ended_at.isoformat() if self._session.ended_at else 'N/A'}",
            "",
            "=" * 60,
            "TRANSCRIPT",
            "=" * 60,
            "",
        ]

        # Collect all utterances and sort by time
        all_utterances: list[tuple[int, CapturedUtterance]] = []
        for user_id, user_capture in self._session.users.items():
            for utt in user_capture.utterances:
                all_utterances.append((user_id, utt))

        all_utterances.sort(key=lambda x: x[1].start_ms)

        for user_id, utt in all_utterances:
            start_sec = utt.start_ms / 1000
            end_sec = utt.end_ms / 1000
            lines.append(f"[{start_sec:.1f}s - {end_sec:.1f}s] User {user_id}:")
            lines.append(f"  {utt.stt_text}")
            lines.append("")

        lines.extend(
            [
                "=" * 60,
                "STATS",
                "=" * 60,
                f"Total raw audio: {self._session.total_raw_audio_ms / 1000:.1f}s",
                f"Speech detected: {self._session.total_speech_detected_ms / 1000:.1f}s",
                f"Utterances transcribed: {self._session.total_utterances}",
                f"Utterances filtered: {self._session.total_utterances_filtered}",
            ]
        )

        transcript_path = self._session_dir / "transcript.txt"
        transcript_path.write_text("\n".join(lines))
