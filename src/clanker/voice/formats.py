"""Audio format definitions for the voice pipeline.

The SDK expects mono PCM audio. External sources (Discord, files, etc.)
must convert to SDK_FORMAT before passing audio to the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioFormat:
    """Describes PCM audio format.

    Attributes:
        sample_rate_hz: Sample rate in Hz (e.g., 48000, 16000)
        channels: Number of audio channels (1=mono, 2=stereo)
        sample_width: Bytes per sample per channel (2 for 16-bit)
    """

    sample_rate_hz: int
    channels: int
    sample_width: int = 2  # 16-bit PCM

    @property
    def bytes_per_sample(self) -> int:
        """Total bytes per sample frame (all channels)."""
        return self.channels * self.sample_width

    @property
    def bytes_per_second(self) -> int:
        """Bytes per second of audio."""
        return self.sample_rate_hz * self.bytes_per_sample

    def bytes_to_ms(self, num_bytes: int) -> float:
        """Convert byte count to milliseconds."""
        if num_bytes == 0:
            return 0.0
        return (num_bytes / self.bytes_per_sample) / self.sample_rate_hz * 1000

    def ms_to_bytes(self, ms: float) -> int:
        """Convert milliseconds to byte count (aligned to sample boundary)."""
        samples = int(ms / 1000 * self.sample_rate_hz)
        return samples * self.bytes_per_sample

    def validate_alignment(self, pcm_bytes: bytes) -> None:
        """Raise ValueError if bytes aren't aligned to sample boundary."""
        if len(pcm_bytes) % self.bytes_per_sample != 0:
            raise ValueError(
                f"PCM data ({len(pcm_bytes)} bytes) not aligned to "
                f"{self.bytes_per_sample}-byte sample boundary for {self}"
            )


# =============================================================================
# Common Audio Formats
# =============================================================================

# Discord voice delivers stereo 48kHz 16-bit PCM
DISCORD_FORMAT = AudioFormat(sample_rate_hz=48000, channels=2)

# SDK internal format - mono 48kHz 16-bit PCM (what the pipeline expects)
SDK_FORMAT = AudioFormat(sample_rate_hz=48000, channels=1)

# Whisper STT expects mono 16kHz 16-bit PCM
WHISPER_FORMAT = AudioFormat(sample_rate_hz=16000, channels=1)
