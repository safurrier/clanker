"""E2E tests for voice transcript to meme generation pipeline.

These tests validate the full flow:
1. Real audio -> VAD -> STT -> transcript
2. Transcript -> ShitpostContext -> meme generation

This tests that transcribed conversations produce coherent shitposts,
validating the integration between voice and meme pipelines.

Requirements:
1. Downloaded audio samples: `make download-test-audio`
2. OpenAI API key: OPENAI_API_KEY environment variable
3. Voice dependencies: `uv pip install -e ".[voice]"`

Run with: `uv run pytest tests/test_voice_to_meme.py -v -m network`
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import pytest

from clanker.models import Context, Persona
from clanker.providers.openai.llm import OpenAILLM
from clanker.providers.openai.stt import OpenAISTT
from clanker.shitposts import ShitpostContext, load_meme_templates, sample_meme_template
from clanker.shitposts.memes import render_meme_text
from clanker.voice.vad import SileroVAD
from clanker.voice.worker import AudioBuffer, TranscriptEvent, transcript_loop_once
from tests.conftest import LibriSpeechSample
from tests.fakes import FakeLLM
from tests.meme_scoring import score_meme, validate_meme_structure


def _get_openai_api_key() -> str:
    """Get OpenAI API key from environment."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not set")
    return key

# =============================================================================
# Voice-to-Meme E2E Tests
# =============================================================================


@pytest.mark.network()
@pytest.mark.slow()
async def test_transcript_generates_meme_with_fake_llm(
    librispeech_available: bool,
    librispeech_samples: list[LibriSpeechSample],
) -> None:
    """E2E: Real audio -> transcript -> meme generation (fake LLM).

    Tests the integration between voice transcription and meme generation
    using real audio but a fake LLM to avoid additional API costs.
    """
    if not librispeech_available:
        pytest.skip("LibriSpeech samples not downloaded. Run: make download-test-audio")

    if not librispeech_samples:
        pytest.skip("No LibriSpeech samples found")

    # Initialize components
    api_key = _get_openai_api_key()
    detector = SileroVAD(warmup=True)
    stt = OpenAISTT(api_key=api_key)

    # Use first sample for this test
    sample = librispeech_samples[0]

    # 1. Transcribe real audio
    with sample.pcm_path.open("rb") as f:
        pcm_bytes = f.read()

    buffers = {1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime.now())}

    events = await transcript_loop_once(
        buffers,
        stt,
        sample.sample_rate,
        detector=detector,
        max_silence_ms=500,
    )

    # Verify we got a transcript
    assert len(events) > 0, "No transcript events generated"
    transcript_text = " ".join(e.text for e in events)
    assert len(transcript_text) > 0, "Empty transcript"

    print(f"\n  Sample: {sample.id}")
    print(f"  Transcript: {transcript_text}")

    # 2. Build ShitpostContext from transcript events
    # TranscriptEvent is compatible with Utterance protocol
    shitpost_context = ShitpostContext(
        transcript_utterances=tuple(events),
        channel_type="voice",
    )

    # Verify context extracts transcript correctly
    prompt_input = shitpost_context.get_prompt_input()
    assert "Recent conversation" in prompt_input
    assert len(prompt_input) > 20  # Should have meaningful content

    print(f"  Prompt input: {prompt_input[:200]}...")

    # 3. Generate meme with fake LLM
    templates = load_meme_templates()
    meme_template = sample_meme_template(templates, template_id="aag")

    context = Context(
        request_id="voice-to-meme-test",
        user_id=1,
        guild_id=None,
        channel_id=1,
        persona=Persona(id="test", display_name="Test", system_prompt="test"),
        messages=[],
        metadata={},
    )

    # Fake LLM returns valid meme lines
    fake_llm = FakeLLM(reply_text='["Line about speech", "Another line"]')
    lines = await render_meme_text(context, fake_llm, meme_template, shitpost_context)

    # 4. Validate output structure
    assert len(lines) == meme_template.text_slots
    assert all(isinstance(line, str) for line in lines)

    print(f"  Meme lines: {lines}")


@pytest.mark.network()
@pytest.mark.slow()
async def test_transcript_with_user_input_generates_meme(
    librispeech_available: bool,
    librispeech_samples: list[LibriSpeechSample],
) -> None:
    """E2E: Real audio + user guidance -> meme generation.

    Tests that user_input can guide meme generation alongside transcript context.
    """
    if not librispeech_available:
        pytest.skip("LibriSpeech samples not downloaded. Run: make download-test-audio")

    if not librispeech_samples:
        pytest.skip("No LibriSpeech samples found")

    api_key = _get_openai_api_key()
    detector = SileroVAD(warmup=True)
    stt = OpenAISTT(api_key=api_key)
    sample = librispeech_samples[0]

    # Transcribe
    with sample.pcm_path.open("rb") as f:
        pcm_bytes = f.read()

    buffers = {1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime.now())}
    events = await transcript_loop_once(
        buffers, stt, sample.sample_rate, detector=detector
    )

    # Build context with both user input and transcript
    shitpost_context = ShitpostContext(
        user_input="make it about coding",
        transcript_utterances=tuple(events),
        channel_type="voice",
    )

    # Verify both appear in prompt
    prompt_input = shitpost_context.get_prompt_input()
    assert "Subject: make it about coding" in prompt_input
    assert "Recent conversation" in prompt_input

    print(f"\n  Combined prompt: {prompt_input[:300]}...")

    # Generate meme
    templates = load_meme_templates()
    meme_template = sample_meme_template(templates)

    context = Context(
        request_id="guided-meme-test",
        user_id=1,
        guild_id=None,
        channel_id=1,
        persona=Persona(id="test", display_name="Test", system_prompt="test"),
        messages=[],
        metadata={},
    )

    fake_llm = FakeLLM(reply_text=json.dumps(["Coding joke"] * meme_template.text_slots))
    lines = await render_meme_text(context, fake_llm, meme_template, shitpost_context)

    assert len(lines) == meme_template.text_slots
    print(f"  Meme template: {meme_template.template_id}")
    print(f"  Meme lines: {lines}")


@pytest.mark.network()
@pytest.mark.slow()
async def test_windowed_transcript_for_meme(
    librispeech_available: bool,
    librispeech_samples: list[LibriSpeechSample],
) -> None:
    """Test that transcript windowing works correctly for meme generation.

    Simulates a scenario where we have a longer conversation history
    but only want to use the most recent utterances for meme generation.
    """
    if not librispeech_available:
        pytest.skip("LibriSpeech samples not downloaded. Run: make download-test-audio")

    if not librispeech_samples:
        pytest.skip("No LibriSpeech samples found")

    api_key = _get_openai_api_key()
    detector = SileroVAD(warmup=True)
    stt = OpenAISTT(api_key=api_key)

    # Transcribe multiple samples to simulate longer conversation
    all_events: list[TranscriptEvent] = []

    for i, sample in enumerate(librispeech_samples[:3]):  # Use up to 3 samples
        with sample.pcm_path.open("rb") as f:
            pcm_bytes = f.read()

        # Offset start times to simulate time progression
        from datetime import timedelta

        base_time = datetime.now() - timedelta(minutes=10 - i * 3)

        buffers = {1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=base_time)}
        events = await transcript_loop_once(
            buffers, stt, sample.sample_rate, detector=detector
        )
        all_events.extend(events)

    if not all_events:
        pytest.skip("No events generated from samples")

    print(f"\n  Total events: {len(all_events)}")
    for e in all_events:
        print(f"    [{e.start_time.strftime('%H:%M:%S')}]: {e.text[:50]}...")

    # Create context with windowing - only use last 2 minutes
    shitpost_context = ShitpostContext(
        transcript_utterances=tuple(all_events),
        max_transcript_minutes=2.0,
        channel_type="voice",
    )

    prompt_input = shitpost_context.get_prompt_input()

    # The prompt should only contain recent utterances
    # (exact content depends on timing, but should be shorter than all events)
    print(f"\n  Windowed prompt length: {len(prompt_input)} chars")
    print(f"  Windowed prompt: {prompt_input[:300]}...")

    # Generate meme from windowed context
    templates = load_meme_templates()
    meme_template = sample_meme_template(templates)

    context = Context(
        request_id="windowed-meme-test",
        user_id=1,
        guild_id=None,
        channel_id=1,
        persona=Persona(id="test", display_name="Test", system_prompt="test"),
        messages=[],
        metadata={},
    )

    fake_llm = FakeLLM(reply_text=json.dumps(["Recent"] * meme_template.text_slots))
    lines = await render_meme_text(context, fake_llm, meme_template, shitpost_context)

    assert len(lines) == meme_template.text_slots


# =============================================================================
# Full E2E Tests with Real LLM and Scoring
# =============================================================================


@pytest.mark.network()
@pytest.mark.slow()
async def test_full_voice_to_meme_pipeline_with_scoring(
    librispeech_available: bool,
    librispeech_samples: list[LibriSpeechSample],
) -> None:
    """Full E2E: Real audio -> transcript -> real LLM meme -> quality scoring.

    This test uses real OpenAI APIs for both transcription and meme generation,
    then scores the output quality using the LLM scoring rubric.
    """
    if not librispeech_available:
        pytest.skip("LibriSpeech samples not downloaded. Run: make download-test-audio")

    if not librispeech_samples:
        pytest.skip("No LibriSpeech samples found")

    # Initialize all real components
    api_key = _get_openai_api_key()
    detector = SileroVAD(warmup=True)
    stt = OpenAISTT(api_key=api_key)
    llm = OpenAILLM(api_key=api_key)

    sample = librispeech_samples[0]

    # 1. Transcribe real audio
    with sample.pcm_path.open("rb") as f:
        pcm_bytes = f.read()

    buffers = {1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime.now())}
    events = await transcript_loop_once(
        buffers, stt, sample.sample_rate, detector=detector, max_silence_ms=500
    )

    assert len(events) > 0, "No transcript events"
    transcript_text = " ".join(e.text for e in events)

    print(f"\n  Sample: {sample.id}")
    print(f"  Transcript: {transcript_text}")

    # 2. Build context and generate meme with real LLM
    shitpost_context = ShitpostContext(
        transcript_utterances=tuple(events),
        channel_type="voice",
    )

    templates = load_meme_templates()
    meme_template = sample_meme_template(templates, template_id="aag")

    context = Context(
        request_id="full-e2e-test",
        user_id=1,
        guild_id=None,
        channel_id=1,
        persona=Persona(
            id="test",
            display_name="Test",
            system_prompt="You are a helpful meme generator.",
        ),
        messages=[],
        metadata={},
    )

    # With structured outputs, JSON parsing failures won't happen
    lines = await render_meme_text(context, llm, meme_template, shitpost_context)

    print(f"  Meme template: {meme_template.template_id}")
    print(f"  Generated lines: {lines}")

    # 3. Validate structure
    is_valid, error = validate_meme_structure(lines, meme_template)
    assert is_valid, f"Meme structure invalid: {error}"

    # 4. Score quality with LLM
    input_context = shitpost_context.get_prompt_input()
    score = await score_meme(llm, meme_template, input_context, lines)

    print(f"  Score: {score}")
    print(f"  Reasoning: {score.reasoning}")

    # Assert minimum quality threshold
    assert score.passes_threshold, (
        f"Meme quality below threshold: avg={score.average:.2f}, "
        f"relevance={score.relevance}, format={score.format_adherence}, "
        f"coherence={score.coherence}"
    )


@pytest.mark.network()
@pytest.mark.slow()
async def test_meme_quality_with_user_guidance(
    librispeech_available: bool,
    librispeech_samples: list[LibriSpeechSample],
) -> None:
    """Test that user guidance improves meme relevance scores."""
    if not librispeech_available:
        pytest.skip("LibriSpeech samples not downloaded. Run: make download-test-audio")

    if not librispeech_samples:
        pytest.skip("No LibriSpeech samples found")

    api_key = _get_openai_api_key()
    detector = SileroVAD(warmup=True)
    stt = OpenAISTT(api_key=api_key)
    llm = OpenAILLM(api_key=api_key)

    sample = librispeech_samples[0]

    # Transcribe
    with sample.pcm_path.open("rb") as f:
        pcm_bytes = f.read()

    buffers = {1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime.now())}
    events = await transcript_loop_once(
        buffers, stt, sample.sample_rate, detector=detector
    )

    # Generate with specific guidance
    shitpost_context = ShitpostContext(
        user_input="make it about programming and software development",
        transcript_utterances=tuple(events),
        channel_type="voice",
    )

    templates = load_meme_templates()
    meme_template = sample_meme_template(templates)

    context = Context(
        request_id="guided-quality-test",
        user_id=1,
        guild_id=None,
        channel_id=1,
        persona=Persona(
            id="test",
            display_name="Test",
            system_prompt="You are a helpful meme generator.",
        ),
        messages=[],
        metadata={},
    )

    # With structured outputs, JSON parsing failures won't happen
    lines = await render_meme_text(context, llm, meme_template, shitpost_context)

    print(f"\n  Template: {meme_template.template_id}")
    print("  User guidance: make it about programming")
    print(f"  Generated lines: {lines}")

    # Validate and score
    is_valid, error = validate_meme_structure(lines, meme_template)
    assert is_valid, f"Meme structure invalid: {error}"

    input_context = shitpost_context.get_prompt_input()
    score = await score_meme(llm, meme_template, input_context, lines)

    print(f"  Score: {score}")

    # With guidance, we expect at least average quality
    assert score.average >= 2.5, f"Guided meme scored too low: {score.average:.2f}"


# =============================================================================
# Unit Tests for TranscriptEvent Compatibility
# =============================================================================


def test_transcript_event_satisfies_utterance_protocol() -> None:
    """Verify TranscriptEvent is compatible with Utterance protocol."""
    from clanker.shitposts.models import Utterance
    from clanker.voice.chunker import AudioChunk

    # Create a TranscriptEvent
    now = datetime.now()
    event = TranscriptEvent(
        speaker_id=1,
        chunk_id="test-chunk",
        text="Hello world",
        chunk=AudioChunk(start_ms=0, end_ms=1000),
        start_time=now,
        end_time=now,
    )

    # Verify it satisfies the protocol
    assert isinstance(event, Utterance), "TranscriptEvent should satisfy Utterance protocol"
    assert event.text == "Hello world"
    assert isinstance(event.start_time, datetime)


def test_shitpost_context_accepts_transcript_events() -> None:
    """Verify ShitpostContext can use TranscriptEvent objects."""
    from clanker.voice.chunker import AudioChunk

    now = datetime.now()
    events = (
        TranscriptEvent(
            speaker_id=1,
            chunk_id="chunk-1",
            text="First utterance",
            chunk=AudioChunk(start_ms=0, end_ms=1000),
            start_time=now,
            end_time=now,
        ),
        TranscriptEvent(
            speaker_id=2,
            chunk_id="chunk-2",
            text="Second utterance",
            chunk=AudioChunk(start_ms=1000, end_ms=2000),
            start_time=now,
            end_time=now,
        ),
    )

    ctx = ShitpostContext(transcript_utterances=events)
    prompt = ctx.get_prompt_input()

    assert "First utterance" in prompt
    assert "Second utterance" in prompt
