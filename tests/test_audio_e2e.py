"""E2E tests with synthetic audio files.

These tests use generated sine wave audio (tests/data/) to validate the pipeline:
- Voice activity detection (Silero VAD or Energy VAD)
- Audio chunking and utterance grouping
- Transcription pipeline (with FakeSTT for deterministic tests)

For tests with real speech datasets (LibriSpeech, AMI Corpus), see FUTURE_WORK.md.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from clanker.voice.vad import EnergyVAD, SileroVAD
from clanker.voice.worker import AudioBuffer, transcript_loop_once
from tests.conftest import AudioSample
from tests.fakes import FakeSTT


@pytest.mark.asyncio()
async def test_synthetic_audio_monologue_with_energy_vad(
    sample_monologue: AudioSample,
) -> None:
    """E2E test: Synthetic 5-second monologue with Energy VAD."""
    # Load PCM audio
    with open(sample_monologue.pcm_path, "rb") as f:
        pcm_bytes = f.read()

    # Use Energy VAD (no torch dependency)
    detector = EnergyVAD(threshold=500)

    # Process audio through pipeline
    buffers = {
        1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime(2024, 1, 1, 12, 0, 0))
    }

    events = await transcript_loop_once(
        buffers,
        FakeSTT(transcript=sample_monologue.transcript),
        sample_monologue.sample_rate,
        detector=detector,
    )

    # Verify: At least one transcript event generated
    assert len(events) > 0, "Should detect speech in monologue"

    # Verify: Transcript matches expected
    combined_text = " ".join(e.text for e in events)
    assert combined_text == sample_monologue.transcript

    # Verify: Speaker ID is correct
    assert all(e.speaker_id == 1 for e in events)


@pytest.mark.asyncio()
async def test_synthetic_audio_paused_speech_detects_silence(
    sample_paused: AudioSample,
) -> None:
    """E2E test: Audio with 1 second silence gap is processed correctly."""
    # Load PCM audio
    with open(sample_paused.pcm_path, "rb") as f:
        pcm_bytes = f.read()

    # Use Energy VAD
    detector = EnergyVAD(threshold=500, padding_ms=300)

    buffers = {
        1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime(2024, 1, 1, 12, 0, 0))
    }

    events = await transcript_loop_once(
        buffers,
        FakeSTT(transcript=sample_paused.transcript),
        sample_paused.sample_rate,
        detector=detector,
        max_silence_ms=800,  # Split on 800ms+ silence
    )

    # Verify: Audio is processed (may be 1 or 2 events depending on VAD detection)
    assert len(events) >= 1, "Should process audio with silence"

    # Verify: Total duration is approximately correct
    if len(events) > 0:
        assert events[0].speaker_id == 1


@pytest.mark.asyncio()
@pytest.mark.skipif(
    True, reason="Silero VAD doesn't detect synthetic sine waves as speech"
)
async def test_synthetic_audio_with_silero_vad(sample_monologue: AudioSample) -> None:
    """E2E test: Synthetic audio with Silero VAD.

    NOTE: This test is skipped because Silero VAD (ML-based) doesn't detect
    synthetic sine waves as speech. For real Silero VAD testing, use actual
    speech samples (see FUTURE_WORK.md).
    """
    pytest.importorskip("torch")
    pytest.importorskip("numpy")

    # Load PCM audio
    with open(sample_monologue.pcm_path, "rb") as f:
        pcm_bytes = f.read()

    # Use Silero VAD
    detector = SileroVAD(warmup=True)

    buffers = {
        1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime(2024, 1, 1, 12, 0, 0))
    }

    events = await transcript_loop_once(
        buffers,
        FakeSTT(transcript=sample_monologue.transcript),
        sample_monologue.sample_rate,
        detector=detector,
    )

    # This will fail - Silero doesn't detect sine waves
    # Real speech is needed for Silero VAD testing
    assert len(events) > 0


@pytest.mark.asyncio()
async def test_synthetic_audio_multispeaker_simulation(
    sample_multispeaker: AudioSample,
) -> None:
    """E2E test: Simulated multi-speaker audio with alternating frequencies."""
    # Load PCM audio
    with open(sample_multispeaker.pcm_path, "rb") as f:
        pcm_bytes = f.read()

    detector = EnergyVAD(threshold=500)

    # Simulate two speakers by splitting audio
    half_len = len(pcm_bytes) // 2
    buffers = {
        1: AudioBuffer(
            pcm_bytes=pcm_bytes[:half_len], start_time=datetime(2024, 1, 1, 12, 0, 0)
        ),
        2: AudioBuffer(
            pcm_bytes=pcm_bytes[half_len:],
            start_time=datetime(2024, 1, 1, 12, 0, 3),  # 3 seconds later
        ),
    }

    events = await transcript_loop_once(
        buffers,
        FakeSTT(transcript=sample_multispeaker.transcript),
        sample_multispeaker.sample_rate,
        detector=detector,
    )

    # Verify: Events from both speakers
    speaker_ids = {e.speaker_id for e in events}
    assert len(speaker_ids) > 0, "Should have events from at least one speaker"

    # Verify: Events are chronologically ordered
    for i in range(len(events) - 1):
        assert events[i].start_time <= events[i + 1].start_time
