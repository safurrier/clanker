"""E2E tests with real speech audio datasets.

These tests use actual speech recordings with ground-truth transcripts to validate
the full voice capture and transcription pipeline with production-quality audio.

Datasets:
- LibriSpeech test-clean: Clean English speech samples
- AMI Corpus: Multi-speaker meeting recordings

These tests require:
1. Downloaded audio samples: `make download-test-audio`
2. OpenAI API key (for Whisper STT): OPENAI_API_KEY environment variable
3. Voice dependencies: `uv pip install -e ".[voice]"`

Run with: `uv run pytest tests/test_real_audio.py -v -m network`
"""

from __future__ import annotations

from datetime import datetime

import pytest

from tests.conftest import AMIMeetingSample, LibriSpeechSample
from tests.metrics import calculate_wer, calculate_wer_details

# =============================================================================
# LibriSpeech Tests - Single Speaker, Clean Speech
# =============================================================================


@pytest.mark.network()
@pytest.mark.slow()
async def test_librispeech_transcription_accuracy(
    librispeech_available: bool,
    librispeech_samples: list[LibriSpeechSample],
) -> None:
    """Validate transcription accuracy with LibriSpeech samples.

    Tests the full pipeline:
    1. Load real speech audio (PCM)
    2. Run through Silero VAD for speech detection
    3. Transcribe with OpenAI Whisper
    4. Compare against ground truth transcript
    5. Assert WER < 10% for clean speech

    Expected: WER < 10% (Whisper is typically 3-5% on LibriSpeech)
    """
    if not librispeech_available:
        pytest.skip("LibriSpeech samples not downloaded. Run: make download-test-audio")

    if not librispeech_samples:
        pytest.skip("No LibriSpeech samples found")

    # Import voice dependencies
    pytest.importorskip("torch")
    pytest.importorskip("numpy")

    from clanker.providers.openai.stt import OpenAISTT
    from clanker.voice.vad import SileroVAD
    from clanker.voice.worker import AudioBuffer, transcript_loop_once

    # Initialize components
    detector = SileroVAD(warmup=True)
    stt = OpenAISTT()

    results = []
    for sample in librispeech_samples:
        # Load PCM audio
        with sample.pcm_path.open("rb") as f:
            pcm_bytes = f.read()

        # Process through pipeline
        buffers = {
            1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime.now())
        }

        events = await transcript_loop_once(
            buffers,
            stt,
            sample.sample_rate,
            detector=detector,
            max_silence_ms=500,
        )

        # Combine all transcribed text
        hypothesis = " ".join(e.text for e in events)

        # Calculate WER
        wer_details = calculate_wer_details(sample.transcript, hypothesis)

        results.append({
            "sample_id": sample.id,
            "reference": sample.transcript,
            "hypothesis": hypothesis,
            "wer": wer_details["wer"],
            "events": len(events),
        })

        print(f"\n  Sample: {sample.id}")
        print(f"  Reference: {sample.transcript}")
        print(f"  Hypothesis: {hypothesis}")
        print(f"  WER: {wer_details['wer']:.2%}")

    # Verify overall accuracy
    avg_wer = sum(r["wer"] for r in results) / len(results)
    print(f"\n  Average WER: {avg_wer:.2%}")

    # Assert acceptable accuracy (10% threshold for clean speech)
    assert avg_wer < 0.10, f"Average WER {avg_wer:.2%} exceeds 10% threshold"

    # Verify all samples produced transcripts
    for result in results:
        assert result["events"] > 0, f"No speech detected in {result['sample_id']}"


@pytest.mark.network()
@pytest.mark.slow()
async def test_librispeech_vad_detects_real_speech(
    librispeech_available: bool,
    librispeech_samples: list[LibriSpeechSample],
) -> None:
    """Verify Silero VAD correctly detects speech in real audio.

    This tests that the ML-based VAD (which doesn't detect synthetic sine waves)
    properly identifies human speech in real recordings.
    """
    if not librispeech_available:
        pytest.skip("LibriSpeech samples not downloaded. Run: make download-test-audio")

    if not librispeech_samples:
        pytest.skip("No LibriSpeech samples found")

    pytest.importorskip("torch")
    pytest.importorskip("numpy")

    from clanker.voice.vad import SileroVAD

    detector = SileroVAD(warmup=True)

    for sample in librispeech_samples:
        with sample.pcm_path.open("rb") as f:
            pcm_bytes = f.read()

        segments = detector.detect(pcm_bytes, sample.sample_rate)

        # Real speech should be detected
        assert len(segments) > 0, f"No speech detected in {sample.id}"

        # Segments should cover a reasonable portion of the audio
        total_speech_ms = sum(s.end_ms - s.start_ms for s in segments)
        audio_duration_ms = len(pcm_bytes) / 2 / sample.sample_rate * 1000

        # At least 30% of audio should be detected as speech
        speech_ratio = total_speech_ms / audio_duration_ms
        assert speech_ratio > 0.30, (
            f"Only {speech_ratio:.1%} of {sample.id} detected as speech"
        )

        print(f"  {sample.id}: {len(segments)} segments, {speech_ratio:.1%} speech")


@pytest.mark.network()
@pytest.mark.slow()
async def test_librispeech_timestamp_accuracy(
    librispeech_available: bool,
    librispeech_samples: list[LibriSpeechSample],
) -> None:
    """Verify VAD timestamps are reasonable for real speech.

    Checks that:
    1. Speech starts near the beginning (not delayed)
    2. Speech ends near the audio end (not truncated)
    3. Segment boundaries are aligned to window size (32ms at 16kHz)
    """
    if not librispeech_available:
        pytest.skip("LibriSpeech samples not downloaded. Run: make download-test-audio")

    if not librispeech_samples:
        pytest.skip("No LibriSpeech samples found")

    pytest.importorskip("torch")
    pytest.importorskip("numpy")

    from clanker.voice.vad import SileroVAD

    detector = SileroVAD(warmup=True)
    window_ms = 32  # Expected window size at 16kHz

    for sample in librispeech_samples:
        with sample.pcm_path.open("rb") as f:
            pcm_bytes = f.read()

        segments = detector.detect(pcm_bytes, sample.sample_rate)

        if not segments:
            pytest.fail(f"No speech detected in {sample.id}")

        # First segment should start within first 500ms
        assert segments[0].start_ms < 500, (
            f"Speech starts too late: {segments[0].start_ms}ms in {sample.id}"
        )

        # Last segment should end within 500ms of audio end
        audio_duration_ms = len(pcm_bytes) / 2 / sample.sample_rate * 1000
        last_end = segments[-1].end_ms
        gap_at_end = audio_duration_ms - last_end
        assert gap_at_end < 500, (
            f"Speech ends too early: {gap_at_end:.0f}ms gap in {sample.id}"
        )

        # All timestamps should be aligned to window size
        for segment in segments:
            assert segment.start_ms % window_ms == 0, (
                f"start_ms={segment.start_ms} not aligned to {window_ms}ms"
            )
            assert segment.end_ms % window_ms == 0, (
                f"end_ms={segment.end_ms} not aligned to {window_ms}ms"
            )


# =============================================================================
# AMI Corpus Tests - Multi-Speaker Meetings
# =============================================================================


@pytest.mark.network()
@pytest.mark.slow()
async def test_ami_multispeaker_detection(
    ami_available: bool,
    ami_meeting_sample: AMIMeetingSample | None,
) -> None:
    """Test multi-speaker detection with AMI Corpus meeting audio.

    Validates that:
    1. Each speaker's audio produces transcript events
    2. Events are correctly associated with speaker IDs
    3. Events from different speakers are chronologically ordered
    """
    if not ami_available or ami_meeting_sample is None:
        pytest.skip("AMI samples not downloaded. Run: make download-test-audio")

    pytest.importorskip("torch")
    pytest.importorskip("numpy")

    from clanker.voice.vad import SileroVAD
    from clanker.voice.worker import AudioBuffer, transcript_loop_once
    from tests.fakes import FakeSTT

    detector = SileroVAD(warmup=True)
    stt = FakeSTT(transcript="speaker utterance")

    # Build buffers for each speaker
    buffers = {}
    base_time = datetime(2024, 1, 1, 12, 0, 0)

    for speaker in ami_meeting_sample.speakers:
        with speaker.pcm_path.open("rb") as f:
            pcm_bytes = f.read()

        # Use speaker index as speaker_id
        speaker_id = speaker.speaker_index + 1
        buffers[speaker_id] = AudioBuffer(
            pcm_bytes=pcm_bytes,
            start_time=base_time,
        )

    # Process all speakers
    events = await transcript_loop_once(
        buffers,
        stt,
        ami_meeting_sample.sample_rate,
        detector=detector,
        max_silence_ms=500,
    )

    # Verify events from multiple speakers
    speaker_ids = {e.speaker_id for e in events}
    print(f"\n  Meeting: {ami_meeting_sample.meeting_id}")
    print(f"  Speakers detected: {len(speaker_ids)}")
    print(f"  Total events: {len(events)}")

    # Should detect events from at least 2 speakers
    # (synthetic samples have 4 speakers)
    assert len(speaker_ids) >= 2, (
        f"Only {len(speaker_ids)} speakers detected, expected at least 2"
    )

    # Events should be chronologically sorted
    for i in range(len(events) - 1):
        assert events[i].start_time <= events[i + 1].start_time, (
            f"Events not chronologically sorted at index {i}"
        )


@pytest.mark.network()
@pytest.mark.slow()
async def test_ami_multispeaker_with_real_stt(
    ami_available: bool,
    ami_meeting_sample: AMIMeetingSample | None,
) -> None:
    """Full E2E test with AMI Corpus using real STT.

    This test uses OpenAI Whisper for transcription to validate
    the complete multi-speaker pipeline with real audio.
    """
    if not ami_available or ami_meeting_sample is None:
        pytest.skip("AMI samples not downloaded. Run: make download-test-audio")

    pytest.importorskip("torch")
    pytest.importorskip("numpy")

    from clanker.providers.openai.stt import OpenAISTT
    from clanker.voice.vad import SileroVAD
    from clanker.voice.worker import AudioBuffer, transcript_loop_once

    detector = SileroVAD(warmup=True)
    stt = OpenAISTT()

    buffers = {}
    base_time = datetime(2024, 1, 1, 12, 0, 0)

    for speaker in ami_meeting_sample.speakers:
        with speaker.pcm_path.open("rb") as f:
            pcm_bytes = f.read()

        speaker_id = speaker.speaker_index + 1
        buffers[speaker_id] = AudioBuffer(
            pcm_bytes=pcm_bytes,
            start_time=base_time,
        )

    events = await transcript_loop_once(
        buffers,
        stt,
        ami_meeting_sample.sample_rate,
        detector=detector,
        max_silence_ms=500,
    )

    print(f"\n  Meeting: {ami_meeting_sample.meeting_id}")
    print(f"  Total events: {len(events)}")

    # Print conversation transcript
    print("\n  Conversation:")
    for event in events:
        print(f"    [Speaker {event.speaker_id}]: {event.text}")

    # Verify we got transcripts
    assert len(events) > 0, "No transcript events generated"

    # Verify transcripts have content
    non_empty_events = [e for e in events if e.text.strip()]
    assert len(non_empty_events) > 0, "All transcripts are empty"


@pytest.mark.network()
@pytest.mark.slow()
async def test_ami_speaker_isolation(
    ami_available: bool,
    ami_meeting_sample: AMIMeetingSample | None,
) -> None:
    """Verify individual speaker audio is properly isolated.

    Each speaker's audio should produce events only for that speaker.
    This validates the per-speaker buffer handling.
    """
    if not ami_available or ami_meeting_sample is None:
        pytest.skip("AMI samples not downloaded. Run: make download-test-audio")

    pytest.importorskip("torch")
    pytest.importorskip("numpy")

    from clanker.voice.vad import SileroVAD
    from clanker.voice.worker import AudioBuffer, transcript_loop_once
    from tests.fakes import FakeSTT

    detector = SileroVAD(warmup=True)

    for speaker in ami_meeting_sample.speakers:
        # Process each speaker individually
        with speaker.pcm_path.open("rb") as f:
            pcm_bytes = f.read()

        speaker_id = speaker.speaker_index + 100  # Unique ID
        stt = FakeSTT(transcript=f"speaker_{speaker.speaker}")

        buffers = {
            speaker_id: AudioBuffer(
                pcm_bytes=pcm_bytes,
                start_time=datetime.now(),
            )
        }

        events = await transcript_loop_once(
            buffers,
            stt,
            speaker.sample_rate,
            detector=detector,
        )

        # All events should be from this speaker
        for event in events:
            assert event.speaker_id == speaker_id, (
                f"Event from wrong speaker: {event.speaker_id} != {speaker_id}"
            )

        print(f"  Speaker {speaker.speaker}: {len(events)} events")


# =============================================================================
# Metrics Tests (Unit Tests for WER Calculation)
# =============================================================================


def test_wer_perfect_match() -> None:
    """WER should be 0 for identical strings."""
    assert calculate_wer("hello world", "hello world") == 0.0


def test_wer_completely_different() -> None:
    """WER should be 1.0 when all words are wrong."""
    assert calculate_wer("hello world", "foo bar") == 1.0


def test_wer_partial_match() -> None:
    """WER should reflect partial matches."""
    wer = calculate_wer("the cat sat on the mat", "the dog sat on the mat")
    assert 0 < wer < 1
    # One word wrong out of 6 = ~0.167
    assert abs(wer - 1 / 6) < 0.01


def test_wer_normalization() -> None:
    """WER should normalize punctuation and case."""
    # These should be considered identical after normalization
    wer = calculate_wer(
        "Hello, World!",
        "hello world"
    )
    assert wer == 0.0


def test_wer_details() -> None:
    """WER details should provide breakdown."""
    details = calculate_wer_details(
        "the quick brown fox",
        "the slow brown dog"  # 2 substitutions: quick->slow, fox->dog
    )
    assert details["substitutions"] == 2
    assert details["insertions"] == 0
    assert details["deletions"] == 0
    assert details["wer"] == 0.5  # 2 errors / 4 words


def test_wer_insertions() -> None:
    """WER should count insertions."""
    details = calculate_wer_details(
        "hello world",
        "hello big world"  # 1 insertion
    )
    assert details["insertions"] == 1


def test_wer_deletions() -> None:
    """WER should count deletions."""
    details = calculate_wer_details(
        "hello big world",
        "hello world"  # 1 deletion
    )
    assert details["deletions"] == 1
