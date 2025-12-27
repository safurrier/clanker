"""Tests for voice pipeline debug capture."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from clanker.voice.debug import (
    CapturedUtterance,
    DebugCapture,
    DebugConfig,
    DebugSession,
    UserCapture,
)
from clanker.voice.vad import SpeechSegment


class TestDebugConfig:
    def test_creates_frozen_config(self) -> None:
        config = DebugConfig(
            sample_rate_hz=48000,
            chunk_seconds=10.0,
            max_silence_ms=1000,
            min_utterance_ms=500,
            vad_type="silero",
        )
        assert config.sample_rate_hz == 48000
        assert config.vad_type == "silero"


class TestDebugSession:
    def test_to_dict_serializable(self) -> None:
        session = DebugSession(
            session_id="test_session",
            started_at=datetime(2024, 1, 15, 14, 30, 0),
            config=DebugConfig(
                sample_rate_hz=48000,
                chunk_seconds=10.0,
                max_silence_ms=1000,
                min_utterance_ms=500,
                vad_type="silero",
            ),
        )
        data = session.to_dict()
        # Should be JSON serializable
        json_str = json.dumps(data)
        assert "test_session" in json_str
        assert "48000" in json_str


class TestUserCapture:
    def test_to_dict_with_utterances(self) -> None:
        user = UserCapture(
            user_id=123,
            raw_buffer_path="users/123/raw.pcm",
            raw_buffer_wav_path="users/123/raw.wav",
            raw_buffer_bytes=1000,
            raw_buffer_duration_ms=500,
            vad_segments=[SpeechSegment(start_ms=0, end_ms=500)],
        )
        user.utterances.append(
            CapturedUtterance(
                user_id=123,
                index=0,
                start_ms=0,
                end_ms=500,
                duration_ms=500,
                wav_original_path="users/123/utt/0/audio.wav",
                wav_16khz_path="users/123/utt/0/audio_16khz.wav",
                source_segments=(SpeechSegment(start_ms=0, end_ms=500),),
                stt_model="whisper-1",
                stt_text="hello world",
                stt_latency_ms=150.0,
            )
        )

        data = user.to_dict()
        assert data["user_id"] == 123
        assert len(data["utterances"]) == 1
        assert data["utterances"][0]["stt_text"] == "hello world"


class TestDebugCaptureFromEnv:
    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VOICE_DEBUG", raising=False)
        capture = DebugCapture.from_env()
        assert capture.enabled is False

    def test_enabled_with_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VOICE_DEBUG", "1")
        capture = DebugCapture.from_env()
        assert capture.enabled is True

    def test_custom_output_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VOICE_DEBUG", "1")
        monkeypatch.setenv("VOICE_DEBUG_DIR", "/custom/path")
        capture = DebugCapture.from_env()
        assert capture.output_dir == Path("/custom/path")


class TestDebugCaptureDisabled:
    """Tests for when debug capture is disabled."""

    def test_start_session_noop_when_disabled(self) -> None:
        capture = DebugCapture(output_dir=Path("/tmp"), enabled=False)
        config = DebugConfig(
            sample_rate_hz=48000,
            chunk_seconds=10.0,
            max_silence_ms=1000,
            min_utterance_ms=500,
            vad_type="silero",
        )
        capture.start_session(config)
        assert capture._session is None

    def test_capture_methods_noop_when_disabled(self) -> None:
        capture = DebugCapture(output_dir=Path("/tmp"), enabled=False)
        # These should not raise
        capture.capture_raw_buffer(123, b"\x00" * 100, 48000)
        capture.capture_vad_result(123, [SpeechSegment(0, 100)])
        capture.capture_filtered_utterance(123, 0, 0, 100, "too_short")


class TestDebugCaptureEnabled:
    """Tests for when debug capture is enabled."""

    def test_full_capture_flow(self, tmp_path: Path) -> None:
        """Test the complete capture flow: start -> capture stages -> end."""
        capture = DebugCapture(output_dir=tmp_path, enabled=True)

        # Start session
        config = DebugConfig(
            sample_rate_hz=48000,
            chunk_seconds=10.0,
            max_silence_ms=1000,
            min_utterance_ms=500,
            vad_type="silero",
        )
        capture.start_session(config)

        assert capture._session is not None
        assert capture._session_dir is not None
        session_dir = capture._session_dir

        # Capture raw buffer
        pcm_data = b"\x00\x10" * 4800  # 100ms at 48kHz
        capture.capture_raw_buffer(123, pcm_data, 48000)

        assert 123 in capture._session.users
        assert (session_dir / "users/123/raw_buffer.pcm").exists()
        assert (session_dir / "users/123/raw_buffer.wav").exists()

        # Capture VAD result
        segments = [
            SpeechSegment(start_ms=0, end_ms=50),
            SpeechSegment(start_ms=60, end_ms=100),
        ]
        capture.capture_vad_result(123, segments)

        assert (session_dir / "users/123/vad_segments.json").exists()
        assert len(capture._session.users[123].vad_segments) == 2

        # Capture filtered utterance
        capture.capture_filtered_utterance(123, 0, 0, 50, "too_short")
        assert capture._session.users[123].utterances_filtered_count == 1

        # Capture utterance audio (need to create wav bytes)
        from clanker.providers.audio_utils import _wrap_pcm_as_wav

        wav_bytes = _wrap_pcm_as_wav(pcm_data, 48000)
        capture.capture_utterance(
            user_id=123,
            index=1,
            wav_bytes=wav_bytes,
            sample_rate_hz=48000,
            start_ms=60,
            end_ms=100,
            source_segments=segments[1:],
        )

        assert (session_dir / "users/123/utterances/1/audio_48000hz.wav").exists()
        assert (session_dir / "users/123/utterances/1/audio_16khz.wav").exists()

        # Capture STT result
        capture.capture_stt_result(
            user_id=123,
            index=1,
            text="hello world",
            latency_ms=150.0,
        )

        assert (session_dir / "users/123/utterances/1/stt_result.json").exists()
        assert len(capture._session.users[123].utterances) == 1
        assert capture._session.users[123].utterances[0].stt_text == "hello world"

        # End session
        result_dir = capture.end_session()

        assert result_dir == session_dir
        assert (session_dir / "manifest.json").exists()
        assert (session_dir / "transcript.txt").exists()

        # Verify manifest content
        manifest = json.loads((session_dir / "manifest.json").read_text())
        assert manifest["config"]["sample_rate_hz"] == 48000
        assert "123" in manifest["users"]
        assert manifest["stats"]["total_utterances"] == 1
        assert manifest["stats"]["total_utterances_filtered"] == 1

    def test_manifest_json_valid(self, tmp_path: Path) -> None:
        """Verify manifest is valid JSON and contains expected fields."""
        capture = DebugCapture(output_dir=tmp_path, enabled=True)
        config = DebugConfig(
            sample_rate_hz=16000,
            chunk_seconds=5.0,
            max_silence_ms=500,
            min_utterance_ms=200,
            vad_type="energy",
        )
        capture.start_session(config)
        capture.capture_raw_buffer(456, b"\x00" * 100, 16000)
        session_dir = capture.end_session()

        assert session_dir is not None
        manifest = json.loads((session_dir / "manifest.json").read_text())

        assert "session_id" in manifest
        assert "started_at" in manifest
        assert "ended_at" in manifest
        assert "config" in manifest
        assert "users" in manifest
        assert "stats" in manifest

    def test_transcript_file_readable(self, tmp_path: Path) -> None:
        """Verify transcript.txt is human-readable."""
        capture = DebugCapture(output_dir=tmp_path, enabled=True)
        config = DebugConfig(
            sample_rate_hz=48000,
            chunk_seconds=10.0,
            max_silence_ms=1000,
            min_utterance_ms=500,
            vad_type="silero",
        )
        capture.start_session(config)

        # Add a complete utterance
        from clanker.providers.audio_utils import _wrap_pcm_as_wav

        pcm = b"\x00\x10" * 4800
        capture.capture_raw_buffer(123, pcm, 48000)
        capture.capture_vad_result(123, [SpeechSegment(0, 100)])
        capture.capture_utterance(123, 0, _wrap_pcm_as_wav(pcm, 48000), 48000, 0, 100, [])
        capture.capture_stt_result(123, 0, "Test transcription", 100.0)

        session_dir = capture.end_session()
        assert session_dir is not None

        transcript = (session_dir / "transcript.txt").read_text()
        assert "TRANSCRIPT" in transcript
        assert "Test transcription" in transcript
        assert "User 123" in transcript


class TestDebugCaptureIntegration:
    """Integration tests with the worker pipeline."""

    @pytest.mark.asyncio
    async def test_captures_during_transcript_loop(self, tmp_path: Path) -> None:
        """Test that debug capture integrates with transcript_loop_once."""
        from clanker.voice.debug import DebugCapture, DebugConfig
        from clanker.voice.vad import EnergyVAD
        from clanker.voice.worker import AudioBuffer, transcript_loop_once
        from tests.fakes import FakeSTT

        capture = DebugCapture(output_dir=tmp_path, enabled=True)
        config = DebugConfig(
            sample_rate_hz=16000,
            chunk_seconds=1.0,
            max_silence_ms=500,
            min_utterance_ms=100,
            vad_type="energy",
        )
        capture.start_session(config)

        # Create audio buffer with some non-silence
        # EnergyVAD uses RMS threshold of 500, so we need loud samples
        # 16-bit samples range from -32768 to 32767
        loud_samples = bytes([0x00, 0x40] * 8000)  # 0x4000 = 16384, above threshold
        buffer = AudioBuffer(pcm_bytes=loud_samples, start_time=datetime.now())

        stt = FakeSTT(transcript="captured text")
        detector = EnergyVAD(threshold=100)  # Lower threshold for test

        events = await transcript_loop_once(
            buffers={999: buffer},
            stt=stt,
            sample_rate_hz=16000,
            detector=detector,
            max_silence_ms=500,
            min_utterance_ms=100,
            debug_capture=capture,
        )

        session_dir = capture.end_session()

        # Verify files were created
        assert session_dir is not None
        assert (session_dir / "users/999").exists()
        assert (session_dir / "manifest.json").exists()

        # If we got events, verify they were captured
        if events:
            manifest = json.loads((session_dir / "manifest.json").read_text())
            assert "999" in manifest["users"]
