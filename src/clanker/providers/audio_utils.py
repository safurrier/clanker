"""Audio processing utilities for STT providers."""

from __future__ import annotations

import array
import audioop
import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clanker.voice.formats import AudioFormat


def resample_wav(wav_bytes: bytes, from_rate: int, to_rate: int) -> bytes:
    """Resample WAV audio to a target sample rate.

    Args:
        wav_bytes: WAV file bytes (with header)
        from_rate: Source sample rate in Hz
        to_rate: Target sample rate in Hz

    Returns:
        New WAV bytes at the target sample rate
    """
    if from_rate == to_rate:
        return wav_bytes

    # WAV header is 44 bytes for standard PCM format
    # Extract PCM data after header
    if len(wav_bytes) < 44:
        raise ValueError("WAV data too short to contain valid header")

    pcm_data = wav_bytes[44:]

    # Resample using audioop (stdlib)
    # Parameters: fragment, width (2 = 16-bit), nchannels, inrate, outrate, state
    resampled_pcm, _ = audioop.ratecv(
        pcm_data,
        2,  # 16-bit samples = 2 bytes per sample
        1,  # mono
        from_rate,
        to_rate,
        None,  # no state for one-shot conversion
    )

    return _wrap_pcm_as_wav(resampled_pcm, to_rate)


def resample_pcm(pcm_bytes: bytes, from_rate: int, to_rate: int) -> bytes:
    """Resample raw PCM audio to a target sample rate.

    Args:
        pcm_bytes: Raw PCM bytes (16-bit mono)
        from_rate: Source sample rate in Hz
        to_rate: Target sample rate in Hz

    Returns:
        Resampled PCM bytes
    """
    if from_rate == to_rate:
        return pcm_bytes

    resampled, _ = audioop.ratecv(
        pcm_bytes,
        2,  # 16-bit samples
        1,  # mono
        from_rate,
        to_rate,
        None,
    )
    return resampled


def _wrap_pcm_as_wav(pcm_bytes: bytes, sample_rate_hz: int) -> bytes:
    """Wrap raw PCM bytes in a WAV container with proper headers.

    Args:
        pcm_bytes: Raw 16-bit mono PCM audio
        sample_rate_hz: Sample rate in Hz

    Returns:
        Complete WAV file bytes
    """
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


def get_wav_sample_rate(wav_bytes: bytes) -> int:
    """Extract sample rate from WAV header.

    Args:
        wav_bytes: WAV file bytes

    Returns:
        Sample rate in Hz
    """
    if len(wav_bytes) < 28:
        raise ValueError("WAV data too short to contain sample rate")

    # Sample rate is at bytes 24-27 (little-endian uint32)
    return struct.unpack("<I", wav_bytes[24:28])[0]


def get_wav_duration_ms(wav_bytes: bytes) -> int:
    """Calculate duration of WAV audio in milliseconds.

    Args:
        wav_bytes: WAV file bytes

    Returns:
        Duration in milliseconds
    """
    if len(wav_bytes) < 44:
        raise ValueError("WAV data too short")

    sample_rate = get_wav_sample_rate(wav_bytes)
    pcm_size = len(wav_bytes) - 44
    # 16-bit mono = 2 bytes per sample
    num_samples = pcm_size // 2
    return int(num_samples / sample_rate * 1000)


def stereo_to_mono(stereo_pcm: bytes) -> bytes:
    """Convert stereo 16-bit PCM to mono by averaging channels.

    Args:
        stereo_pcm: Raw stereo PCM bytes (4 bytes per sample frame)

    Returns:
        Mono PCM bytes (2 bytes per sample)

    Raises:
        ValueError: If input isn't 4-byte aligned (stereo 16-bit)
    """
    if len(stereo_pcm) % 4 != 0:
        raise ValueError(
            f"Stereo PCM must be 4-byte aligned, got {len(stereo_pcm)} bytes"
        )

    if len(stereo_pcm) == 0:
        return b""

    # Use array module for efficient conversion
    stereo = array.array("h")  # signed 16-bit
    stereo.frombytes(stereo_pcm)

    mono = array.array("h")
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
        ValueError: If conversion is not supported (e.g., mono to stereo)
    """
    from_format.validate_alignment(pcm_bytes)

    result = pcm_bytes
    current_channels = from_format.channels
    current_sample_rate = from_format.sample_rate_hz

    # Step 1: Convert stereo to mono if needed
    if current_channels == 2 and to_format.channels == 1:
        result = stereo_to_mono(result)
        current_channels = 1
    elif current_channels != to_format.channels:
        raise ValueError(
            f"Unsupported channel conversion: {current_channels} -> {to_format.channels}"
        )

    # Step 2: Resample if needed
    if current_sample_rate != to_format.sample_rate_hz:
        result = resample_pcm(result, current_sample_rate, to_format.sample_rate_hz)

    return result
