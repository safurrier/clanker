# Voice Pipeline Fix: AudioFormat Abstraction

## Overview

Implement a clean separation between Discord-specific audio handling (bot layer) and source-agnostic audio processing (SDK layer) using an `AudioFormat` abstraction.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  src/clanker_bot/ (Discord-specific)                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  voice_ingest.py                                     │   │
│  │  - Receives Discord stereo 48kHz                     │   │
│  │  - Converts to SDK format (mono 48kHz)               │   │
│  │  - Passes normalized audio to SDK                    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ mono 48kHz PCM
┌─────────────────────────────────────────────────────────────┐
│  src/clanker/ (SDK - source agnostic)                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  voice/formats.py    - AudioFormat dataclass         │   │
│  │  providers/audio_utils.py - Format conversion        │   │
│  │  voice/worker.py     - Expects SDK_FORMAT (mono)     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Problem Statement

Discord delivers **stereo 48kHz 16-bit PCM** but our SDK assumes **mono**. This causes:
1. 2x timing errors in byte-to-time calculations
2. Corrupted audio when slicing PCM
3. VAD failures from interleaved stereo samples

## Implementation Plan

### Phase 1: SDK Audio Format Contract

#### 1.1 Create `src/clanker/voice/formats.py` (NEW)

```python
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

# Discord voice delivers stereo 48kHz
DISCORD_FORMAT = AudioFormat(sample_rate_hz=48000, channels=2)

# SDK internal format - mono 48kHz (what the pipeline expects)
SDK_FORMAT = AudioFormat(sample_rate_hz=48000, channels=1)

# Whisper STT expects mono 16kHz
WHISPER_FORMAT = AudioFormat(sample_rate_hz=16000, channels=1)
```

#### 1.2 Update `src/clanker/voice/__init__.py`

Add exports for the new format types:

```python
from .formats import AudioFormat, DISCORD_FORMAT, SDK_FORMAT, WHISPER_FORMAT
```

---

### Phase 2: Audio Conversion Utilities

#### 2.1 Add to `src/clanker/providers/audio_utils.py`

```python
import array
from clanker.voice.formats import AudioFormat


def stereo_to_mono(stereo_pcm: bytes) -> bytes:
    """Convert stereo 16-bit PCM to mono by averaging channels.

    Args:
        stereo_pcm: Raw stereo PCM bytes (4 bytes per sample frame)

    Returns:
        Mono PCM bytes (2 bytes per sample)

    Raises:
        ValueError: If input isn't 4-byte aligned (stereo)
    """
    if len(stereo_pcm) % 4 != 0:
        raise ValueError(
            f"Stereo PCM must be 4-byte aligned, got {len(stereo_pcm)} bytes"
        )

    if len(stereo_pcm) == 0:
        return b""

    # Use array module for efficient conversion
    stereo = array.array('h')  # signed 16-bit
    stereo.frombytes(stereo_pcm)

    mono = array.array('h')
    for i in range(0, len(stereo), 2):
        # Average left and right channels
        avg = (stereo[i] + stereo[i + 1]) // 2
        mono.append(avg)

    return mono.tobytes()


def convert_pcm(
    pcm_bytes: bytes,
    from_format: AudioFormat,
    to_format: AudioFormat,
) -> bytes:
    """Convert PCM audio between formats.

    Handles:
    - Stereo to mono conversion (averages channels)
    - Sample rate conversion (via audioop.ratecv)

    Args:
        pcm_bytes: Raw PCM audio in source format
        from_format: Source audio format
        to_format: Target audio format

    Returns:
        PCM audio in target format

    Raises:
        ValueError: If conversion is not supported
    """
    from_format.validate_alignment(pcm_bytes)

    result = pcm_bytes
    current_format = from_format

    # Step 1: Convert stereo to mono if needed
    if current_format.channels == 2 and to_format.channels == 1:
        result = stereo_to_mono(result)
        current_format = AudioFormat(
            sample_rate_hz=current_format.sample_rate_hz,
            channels=1,
            sample_width=current_format.sample_width,
        )
    elif current_format.channels != to_format.channels:
        raise ValueError(
            f"Unsupported channel conversion: {current_format.channels} -> {to_format.channels}"
        )

    # Step 2: Resample if needed
    if current_format.sample_rate_hz != to_format.sample_rate_hz:
        result = resample_pcm(
            result,
            current_format.sample_rate_hz,
            to_format.sample_rate_hz,
        )

    return result
```

---

### Phase 3: Update Voice Ingest (Bot Layer)

#### 3.1 Update `src/clanker_bot/voice_ingest.py`

```python
from clanker.providers.audio_utils import convert_pcm
from clanker.voice.formats import DISCORD_FORMAT, SDK_FORMAT

class VoiceIngestSink(voice_recv.AudioSink):

    def write(self, user: object, data: object) -> None:
        """Write audio data from a user (called from voice_recv thread)."""
        self._frame_count += 1

        # Log format info on first frame for debugging
        if self._frame_count == 1:
            pcm_bytes = getattr(data, "pcm", None)
            if pcm_bytes:
                expected = DISCORD_FORMAT.sample_rate_hz * 0.02 * DISCORD_FORMAT.bytes_per_sample
                logger.info(
                    "voice_sink.format_check: frame_bytes={}, expected_stereo={}, "
                    "discord_format={}",
                    len(pcm_bytes),
                    int(expected),
                    DISCORD_FORMAT,
                )

        if not user or not hasattr(user, "id"):
            return

        pcm_bytes = getattr(data, "pcm", None)
        if pcm_bytes is None:
            return

        # Convert Discord stereo to SDK mono format
        try:
            mono_pcm = convert_pcm(pcm_bytes, DISCORD_FORMAT, SDK_FORMAT)
        except ValueError as e:
            logger.warning("voice_sink.conversion_error: {}", e)
            return

        user_id = int(getattr(user, "id"))
        self._total_bytes += len(mono_pcm)
        self.worker.add_pcm(user_id, mono_pcm)
```

---

### Phase 4: Update SDK Worker

#### 4.1 Update `src/clanker/voice/worker.py`

Add format validation and use SDK_FORMAT for calculations:

```python
from .formats import SDK_FORMAT

def _slice_pcm(pcm_bytes: bytes, sample_rate_hz: int, chunk: AudioChunk) -> bytes:
    """Slice PCM bytes for a chunk and wrap in WAV container.

    Assumes mono PCM matching SDK_FORMAT.
    """
    # Use SDK_FORMAT for byte calculations (mono, 16-bit)
    bytes_per_sample = SDK_FORMAT.bytes_per_sample  # 2 for mono 16-bit
    start_index = int(chunk.start_ms / 1000 * sample_rate_hz) * bytes_per_sample
    end_index = int(chunk.end_ms / 1000 * sample_rate_hz) * bytes_per_sample
    pcm_chunk = pcm_bytes[start_index:end_index]
    return _wrap_pcm_as_wav(pcm_chunk, sample_rate_hz)
```

Also update `VoiceIngestWorker.should_process()`:

```python
def should_process(self) -> bool:
    """Check if any buffer exceeds the chunk size threshold."""
    # Mono 16-bit: 2 bytes per sample
    bytes_per_sample = SDK_FORMAT.bytes_per_sample
    min_bytes = int(self.sample_rate_hz * self.chunk_seconds) * bytes_per_sample
    # ... rest unchanged
```

---

### Phase 5: Tests

#### 5.1 Create `tests/test_audio_formats.py` (NEW)

```python
"""Tests for audio format handling."""

import pytest
from clanker.voice.formats import (
    AudioFormat,
    DISCORD_FORMAT,
    SDK_FORMAT,
    WHISPER_FORMAT,
)
from clanker.providers.audio_utils import stereo_to_mono, convert_pcm


class TestAudioFormat:
    def test_discord_format(self):
        assert DISCORD_FORMAT.sample_rate_hz == 48000
        assert DISCORD_FORMAT.channels == 2
        assert DISCORD_FORMAT.bytes_per_sample == 4

    def test_sdk_format(self):
        assert SDK_FORMAT.sample_rate_hz == 48000
        assert SDK_FORMAT.channels == 1
        assert SDK_FORMAT.bytes_per_sample == 2

    def test_bytes_to_ms(self):
        # 1 second of mono 48kHz = 96000 bytes
        assert SDK_FORMAT.bytes_to_ms(96000) == 1000.0
        # 1 second of stereo 48kHz = 192000 bytes
        assert DISCORD_FORMAT.bytes_to_ms(192000) == 1000.0

    def test_ms_to_bytes(self):
        assert SDK_FORMAT.ms_to_bytes(1000) == 96000
        assert DISCORD_FORMAT.ms_to_bytes(1000) == 192000

    def test_validate_alignment_passes(self):
        SDK_FORMAT.validate_alignment(b"\x00\x00" * 100)  # 200 bytes, aligned

    def test_validate_alignment_fails(self):
        with pytest.raises(ValueError, match="not aligned"):
            SDK_FORMAT.validate_alignment(b"\x00\x00\x00")  # 3 bytes, not aligned


class TestStereoToMono:
    def test_empty_input(self):
        assert stereo_to_mono(b"") == b""

    def test_single_frame(self):
        # Stereo frame: L=100, R=200 -> Mono=150
        import struct
        stereo = struct.pack("<hh", 100, 200)
        mono = stereo_to_mono(stereo)
        assert struct.unpack("<h", mono)[0] == 150

    def test_averaging(self):
        import struct
        # Multiple frames
        stereo = struct.pack("<hhhh", 0, 100, -100, 100)
        mono = stereo_to_mono(stereo)
        values = struct.unpack("<hh", mono)
        assert values == (50, 0)  # (0+100)/2, (-100+100)/2

    def test_misaligned_raises(self):
        with pytest.raises(ValueError, match="4-byte aligned"):
            stereo_to_mono(b"\x00\x00\x00")  # 3 bytes


class TestConvertPcm:
    def test_discord_to_sdk(self):
        """Discord stereo -> SDK mono."""
        import struct
        # 2 stereo frames
        stereo = struct.pack("<hhhh", 100, 200, 300, 400)
        mono = convert_pcm(stereo, DISCORD_FORMAT, SDK_FORMAT)
        values = struct.unpack("<hh", mono)
        assert values == (150, 350)

    def test_same_format_passthrough(self):
        """Same format returns input unchanged."""
        pcm = b"\x00\x00" * 100
        result = convert_pcm(pcm, SDK_FORMAT, SDK_FORMAT)
        assert result == pcm

    def test_with_resampling(self):
        """Conversion with sample rate change."""
        # 1 second of mono 48kHz
        mono_48k = b"\x00\x00" * 48000
        mono_16k = convert_pcm(
            mono_48k,
            SDK_FORMAT,
            WHISPER_FORMAT,
        )
        # Should be ~1 second at 16kHz = 32000 bytes
        assert abs(len(mono_16k) - 32000) < 100  # Allow some tolerance
```

#### 5.2 Update `tests/test_audio_utils.py`

Add tests for the integration with formats.

---

### Phase 6: Implementation Checklist

- [x] **1. Create formats.py** - AudioFormat dataclass + constants
- [x] **2. Update voice/__init__.py** - Export new types
- [x] **3. Add stereo_to_mono()** - To audio_utils.py
- [x] **4. Add convert_pcm()** - To audio_utils.py
- [x] **5. Update voice_ingest.py** - Apply conversion at Discord boundary
- [x] **6. Update worker.py** - Use SDK_FORMAT for byte calculations
- [x] **7. Add tests** - test_audio_formats.py (27 tests)
- [x] **8. Run full test suite** - 50 tests passing
- [ ] **9. Manual test** - Join voice, verify transcription works

---

## Verification

After implementation:

```bash
# Run tests
make check

# Test with debug capture
VOICE_DEBUG=1 python -m clanker_bot

# Join voice channel, speak, then check:
# 1. Logs should show "format_check: frame_bytes=3840" (stereo)
# 2. Debug files should contain proper mono audio
# 3. Transcription should work correctly
```

---

## Files Changed Summary

| File | Change |
|------|--------|
| `src/clanker/voice/formats.py` | **NEW** - AudioFormat dataclass |
| `src/clanker/voice/__init__.py` | Export format types |
| `src/clanker/providers/audio_utils.py` | Add stereo_to_mono, convert_pcm |
| `src/clanker_bot/voice_ingest.py` | Apply format conversion |
| `src/clanker/voice/worker.py` | Use SDK_FORMAT for calculations |
| `tests/test_audio_formats.py` | **NEW** - Format tests |

---

## Future Extensibility

This design supports:
- **File input**: Load WAV, detect format, convert to SDK_FORMAT
- **Other platforms**: Define ZOOM_FORMAT, TEAMS_FORMAT, etc.
- **Different output targets**: Convert to format expected by different STT providers
