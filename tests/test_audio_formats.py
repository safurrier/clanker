"""Tests for audio format handling.

TDD: These tests are written first to define the expected behavior
of the AudioFormat abstraction and conversion utilities.
"""

from __future__ import annotations

import struct

import pytest


class TestAudioFormat:
    """Tests for the AudioFormat dataclass."""

    def test_discord_format_properties(self) -> None:
        """Discord delivers stereo 48kHz 16-bit audio."""
        from clanker.voice.formats import DISCORD_FORMAT

        assert DISCORD_FORMAT.sample_rate_hz == 48000
        assert DISCORD_FORMAT.channels == 2
        assert DISCORD_FORMAT.sample_width == 2
        assert DISCORD_FORMAT.bytes_per_sample == 4  # 2 channels * 2 bytes

    def test_sdk_format_properties(self) -> None:
        """SDK expects mono 48kHz 16-bit audio."""
        from clanker.voice.formats import SDK_FORMAT

        assert SDK_FORMAT.sample_rate_hz == 48000
        assert SDK_FORMAT.channels == 1
        assert SDK_FORMAT.sample_width == 2
        assert SDK_FORMAT.bytes_per_sample == 2  # 1 channel * 2 bytes

    def test_whisper_format_properties(self) -> None:
        """Whisper expects mono 16kHz 16-bit audio."""
        from clanker.voice.formats import WHISPER_FORMAT

        assert WHISPER_FORMAT.sample_rate_hz == 16000
        assert WHISPER_FORMAT.channels == 1
        assert WHISPER_FORMAT.sample_width == 2
        assert WHISPER_FORMAT.bytes_per_sample == 2

    def test_bytes_per_second(self) -> None:
        """Calculate bytes per second of audio."""
        from clanker.voice.formats import DISCORD_FORMAT, SDK_FORMAT

        # Stereo 48kHz: 48000 * 4 = 192000 bytes/sec
        assert DISCORD_FORMAT.bytes_per_second == 192000
        # Mono 48kHz: 48000 * 2 = 96000 bytes/sec
        assert SDK_FORMAT.bytes_per_second == 96000

    def test_bytes_to_ms_mono(self) -> None:
        """Convert byte count to milliseconds for mono audio."""
        from clanker.voice.formats import SDK_FORMAT

        # 1 second of mono 48kHz = 96000 bytes
        assert SDK_FORMAT.bytes_to_ms(96000) == 1000.0
        # 500ms = 48000 bytes
        assert SDK_FORMAT.bytes_to_ms(48000) == 500.0
        # 0 bytes = 0 ms
        assert SDK_FORMAT.bytes_to_ms(0) == 0.0

    def test_bytes_to_ms_stereo(self) -> None:
        """Convert byte count to milliseconds for stereo audio."""
        from clanker.voice.formats import DISCORD_FORMAT

        # 1 second of stereo 48kHz = 192000 bytes
        assert DISCORD_FORMAT.bytes_to_ms(192000) == 1000.0
        # 20ms Discord frame = 3840 bytes
        assert DISCORD_FORMAT.bytes_to_ms(3840) == 20.0

    def test_ms_to_bytes_mono(self) -> None:
        """Convert milliseconds to byte count for mono audio."""
        from clanker.voice.formats import SDK_FORMAT

        assert SDK_FORMAT.ms_to_bytes(1000) == 96000
        assert SDK_FORMAT.ms_to_bytes(500) == 48000
        assert SDK_FORMAT.ms_to_bytes(0) == 0

    def test_ms_to_bytes_stereo(self) -> None:
        """Convert milliseconds to byte count for stereo audio."""
        from clanker.voice.formats import DISCORD_FORMAT

        assert DISCORD_FORMAT.ms_to_bytes(1000) == 192000
        # 20ms Discord frame
        assert DISCORD_FORMAT.ms_to_bytes(20) == 3840

    def test_validate_alignment_mono_passes(self) -> None:
        """Validation passes for properly aligned mono data."""
        from clanker.voice.formats import SDK_FORMAT

        # 100 mono samples = 200 bytes (aligned to 2-byte boundary)
        SDK_FORMAT.validate_alignment(b"\x00\x00" * 100)

    def test_validate_alignment_stereo_passes(self) -> None:
        """Validation passes for properly aligned stereo data."""
        from clanker.voice.formats import DISCORD_FORMAT

        # 100 stereo samples = 400 bytes (aligned to 4-byte boundary)
        DISCORD_FORMAT.validate_alignment(b"\x00\x00\x00\x00" * 100)

    def test_validate_alignment_mono_fails(self) -> None:
        """Validation fails for misaligned mono data."""
        from clanker.voice.formats import SDK_FORMAT

        with pytest.raises(ValueError, match="not aligned"):
            SDK_FORMAT.validate_alignment(b"\x00\x00\x00")  # 3 bytes, not aligned

    def test_validate_alignment_stereo_fails(self) -> None:
        """Validation fails for misaligned stereo data."""
        from clanker.voice.formats import DISCORD_FORMAT

        with pytest.raises(ValueError, match="not aligned"):
            DISCORD_FORMAT.validate_alignment(b"\x00\x00\x00")  # 3 bytes, not aligned

    def test_format_is_frozen(self) -> None:
        """AudioFormat should be immutable."""
        from clanker.voice.formats import AudioFormat

        fmt = AudioFormat(sample_rate_hz=48000, channels=1)
        with pytest.raises(Exception):  # FrozenInstanceError
            fmt.sample_rate_hz = 16000  # type: ignore[misc]


class TestStereoToMono:
    """Tests for stereo to mono conversion."""

    def test_empty_input(self) -> None:
        """Empty input returns empty output."""
        from clanker.providers.audio_utils import stereo_to_mono

        assert stereo_to_mono(b"") == b""

    def test_single_frame_averaging(self) -> None:
        """Single stereo frame is averaged to mono."""
        from clanker.providers.audio_utils import stereo_to_mono

        # Stereo frame: L=100, R=200 -> Mono=(100+200)/2=150
        stereo = struct.pack("<hh", 100, 200)
        mono = stereo_to_mono(stereo)
        assert struct.unpack("<h", mono)[0] == 150

    def test_multiple_frames(self) -> None:
        """Multiple stereo frames are each averaged."""
        from clanker.providers.audio_utils import stereo_to_mono

        # Frame 1: L=0, R=100 -> 50
        # Frame 2: L=-100, R=100 -> 0
        stereo = struct.pack("<hhhh", 0, 100, -100, 100)
        mono = stereo_to_mono(stereo)
        values = struct.unpack("<hh", mono)
        assert values == (50, 0)

    def test_negative_values(self) -> None:
        """Negative sample values are handled correctly."""
        from clanker.providers.audio_utils import stereo_to_mono

        # L=-1000, R=-2000 -> -1500
        stereo = struct.pack("<hh", -1000, -2000)
        mono = stereo_to_mono(stereo)
        assert struct.unpack("<h", mono)[0] == -1500

    def test_max_values(self) -> None:
        """Maximum sample values don't overflow."""
        from clanker.providers.audio_utils import stereo_to_mono

        # L=32767, R=32767 -> 32767 (max int16)
        stereo = struct.pack("<hh", 32767, 32767)
        mono = stereo_to_mono(stereo)
        assert struct.unpack("<h", mono)[0] == 32767

    def test_misaligned_raises(self) -> None:
        """Misaligned input raises ValueError."""
        from clanker.providers.audio_utils import stereo_to_mono

        with pytest.raises(ValueError, match="4-byte aligned"):
            stereo_to_mono(b"\x00\x00\x00")  # 3 bytes, not 4-byte aligned

    def test_output_half_size(self) -> None:
        """Output is exactly half the size of input."""
        from clanker.providers.audio_utils import stereo_to_mono

        stereo = b"\x00\x00\x00\x00" * 1000  # 4000 bytes
        mono = stereo_to_mono(stereo)
        assert len(mono) == 2000


class TestConvertPcm:
    """Tests for PCM format conversion."""

    def test_discord_to_sdk(self) -> None:
        """Convert Discord stereo to SDK mono."""
        from clanker.providers.audio_utils import convert_pcm
        from clanker.voice.formats import DISCORD_FORMAT, SDK_FORMAT

        # 2 stereo frames: (100,200), (300,400)
        stereo = struct.pack("<hhhh", 100, 200, 300, 400)
        mono = convert_pcm(stereo, DISCORD_FORMAT, SDK_FORMAT)
        values = struct.unpack("<hh", mono)
        assert values == (150, 350)

    def test_same_format_passthrough(self) -> None:
        """Same format returns input unchanged."""
        from clanker.providers.audio_utils import convert_pcm
        from clanker.voice.formats import SDK_FORMAT

        pcm = b"\x00\x00" * 100
        result = convert_pcm(pcm, SDK_FORMAT, SDK_FORMAT)
        assert result == pcm

    def test_sdk_to_whisper_resamples(self) -> None:
        """SDK to Whisper format resamples 48kHz to 16kHz."""
        from clanker.providers.audio_utils import convert_pcm
        from clanker.voice.formats import SDK_FORMAT, WHISPER_FORMAT

        # 1 second of mono 48kHz = 96000 bytes
        mono_48k = b"\x00\x00" * 48000
        mono_16k = convert_pcm(mono_48k, SDK_FORMAT, WHISPER_FORMAT)
        # Should be ~1 second at 16kHz = 32000 bytes
        # Allow some tolerance for resampling algorithm
        assert abs(len(mono_16k) - 32000) < 100

    def test_discord_to_whisper_converts_and_resamples(self) -> None:
        """Discord to Whisper: stereo->mono AND 48kHz->16kHz."""
        from clanker.providers.audio_utils import convert_pcm
        from clanker.voice.formats import DISCORD_FORMAT, WHISPER_FORMAT

        # 1 second of stereo 48kHz = 192000 bytes
        stereo_48k = b"\x00\x00\x00\x00" * 48000
        mono_16k = convert_pcm(stereo_48k, DISCORD_FORMAT, WHISPER_FORMAT)
        # Should be ~1 second at 16kHz mono = 32000 bytes
        assert abs(len(mono_16k) - 32000) < 100

    def test_validates_input_alignment(self) -> None:
        """Misaligned input raises ValueError."""
        from clanker.providers.audio_utils import convert_pcm
        from clanker.voice.formats import DISCORD_FORMAT, SDK_FORMAT

        with pytest.raises(ValueError, match="not aligned"):
            convert_pcm(b"\x00\x00\x00", DISCORD_FORMAT, SDK_FORMAT)

    def test_unsupported_mono_to_stereo_raises(self) -> None:
        """Mono to stereo conversion is not supported."""
        from clanker.providers.audio_utils import convert_pcm
        from clanker.voice.formats import DISCORD_FORMAT, SDK_FORMAT

        with pytest.raises(ValueError, match="Unsupported channel conversion"):
            convert_pcm(b"\x00\x00" * 100, SDK_FORMAT, DISCORD_FORMAT)


class TestAudioFormatExports:
    """Test that formats are properly exported from the voice module."""

    def test_exports_from_voice_module(self) -> None:
        """AudioFormat and constants should be exported from clanker.voice."""
        from clanker.voice import (
            AudioFormat,
            DISCORD_FORMAT,
            SDK_FORMAT,
            WHISPER_FORMAT,
        )

        assert AudioFormat is not None
        assert DISCORD_FORMAT is not None
        assert SDK_FORMAT is not None
        assert WHISPER_FORMAT is not None
