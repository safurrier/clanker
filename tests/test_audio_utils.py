"""Tests for audio utility functions."""

from __future__ import annotations

import struct

import pytest

from clanker.providers.audio_utils import (
    get_wav_duration_ms,
    get_wav_sample_rate,
    resample_pcm,
    resample_wav,
    _wrap_pcm_as_wav,
)


def make_test_wav(sample_rate: int, duration_ms: int) -> bytes:
    """Create a test WAV file with a simple tone pattern."""
    num_samples = int(sample_rate * duration_ms / 1000)
    # Create a simple repeating pattern (not silence, to preserve through resampling)
    pcm = bytes([0x00, 0x10, 0x00, 0xF0] * (num_samples // 2))[:num_samples * 2]
    return _wrap_pcm_as_wav(pcm, sample_rate)


class TestWrapPcmAsWav:
    def test_creates_valid_wav_header(self) -> None:
        pcm = b"\x00\x00" * 100  # 100 samples of silence
        wav = _wrap_pcm_as_wav(pcm, 16000)

        # Check RIFF header
        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"
        assert wav[12:16] == b"fmt "
        assert wav[36:40] == b"data"

    def test_wav_length_correct(self) -> None:
        pcm = b"\x00\x00" * 100
        wav = _wrap_pcm_as_wav(pcm, 16000)

        # Total length = 44 byte header + PCM data
        assert len(wav) == 44 + len(pcm)

    def test_sample_rate_in_header(self) -> None:
        pcm = b"\x00\x00" * 100
        wav = _wrap_pcm_as_wav(pcm, 48000)

        # Sample rate is at bytes 24-27 (little-endian)
        rate = struct.unpack("<I", wav[24:28])[0]
        assert rate == 48000


class TestGetWavSampleRate:
    def test_extracts_16khz(self) -> None:
        wav = make_test_wav(16000, 100)
        assert get_wav_sample_rate(wav) == 16000

    def test_extracts_48khz(self) -> None:
        wav = make_test_wav(48000, 100)
        assert get_wav_sample_rate(wav) == 48000

    def test_raises_on_short_data(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            get_wav_sample_rate(b"short")


class TestGetWavDurationMs:
    def test_100ms_at_16khz(self) -> None:
        wav = make_test_wav(16000, 100)
        duration = get_wav_duration_ms(wav)
        # Allow small rounding difference
        assert 98 <= duration <= 102

    def test_1000ms_at_48khz(self) -> None:
        wav = make_test_wav(48000, 1000)
        duration = get_wav_duration_ms(wav)
        assert 998 <= duration <= 1002


class TestResamplePcm:
    def test_no_change_when_same_rate(self) -> None:
        pcm = b"\x00\x00\x10\x00" * 100
        result = resample_pcm(pcm, 16000, 16000)
        assert result == pcm

    def test_downsample_48k_to_16k(self) -> None:
        # 48kHz has 3x the samples of 16kHz for same duration
        pcm_48k = b"\x00\x00" * 4800  # 100ms at 48kHz
        result = resample_pcm(pcm_48k, 48000, 16000)

        # Should be roughly 1/3 the size
        expected_samples = 1600  # 100ms at 16kHz
        # Allow some tolerance for resampling algorithm
        assert abs(len(result) // 2 - expected_samples) < 10

    def test_upsample_16k_to_48k(self) -> None:
        pcm_16k = b"\x00\x00" * 1600  # 100ms at 16kHz
        result = resample_pcm(pcm_16k, 16000, 48000)

        # Should be roughly 3x the size
        expected_samples = 4800  # 100ms at 48kHz
        assert abs(len(result) // 2 - expected_samples) < 10


class TestResampleWav:
    def test_no_change_when_same_rate(self) -> None:
        wav = make_test_wav(16000, 100)
        result = resample_wav(wav, 16000, 16000)
        assert result == wav

    def test_downsample_48k_to_16k_preserves_duration(self) -> None:
        wav_48k = make_test_wav(48000, 500)  # 500ms
        result = resample_wav(wav_48k, 48000, 16000)

        # Output should still be ~500ms
        duration = get_wav_duration_ms(result)
        assert 490 <= duration <= 510

        # But at 16kHz
        rate = get_wav_sample_rate(result)
        assert rate == 16000

    def test_downsample_reduces_file_size(self) -> None:
        wav_48k = make_test_wav(48000, 500)
        wav_16k = resample_wav(wav_48k, 48000, 16000)

        # 16kHz should be ~1/3 the size of 48kHz
        # (minus header which stays same)
        pcm_48k_size = len(wav_48k) - 44
        pcm_16k_size = len(wav_16k) - 44

        ratio = pcm_16k_size / pcm_48k_size
        assert 0.3 <= ratio <= 0.4

    def test_raises_on_invalid_wav(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            resample_wav(b"not a wav file", 48000, 16000)


class TestResamplingIntegration:
    """Integration tests simulating the Discord -> Whisper flow."""

    def test_discord_48k_to_whisper_16k(self) -> None:
        """Simulate the real pipeline: Discord 48kHz -> resample -> Whisper 16kHz."""
        # Create audio as Discord would send it (48kHz)
        discord_pcm = b"\x00\x10\x00\xF0" * 24000  # 1 second at 48kHz
        discord_wav = _wrap_pcm_as_wav(discord_pcm, 48000)

        # Verify input
        assert get_wav_sample_rate(discord_wav) == 48000
        assert 990 <= get_wav_duration_ms(discord_wav) <= 1010

        # Resample for Whisper
        whisper_wav = resample_wav(discord_wav, 48000, 16000)

        # Verify output
        assert get_wav_sample_rate(whisper_wav) == 16000
        # Duration should be preserved (within tolerance)
        assert 990 <= get_wav_duration_ms(whisper_wav) <= 1010
