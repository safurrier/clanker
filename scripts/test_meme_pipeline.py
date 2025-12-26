#!/usr/bin/env python3
"""Test the meme generation and scoring pipeline with real audio samples.

This script runs the full voice-to-meme pipeline on LibriSpeech samples,
reporting detailed results on transcription, meme generation, and quality scoring.

Usage:
    python scripts/test_meme_pipeline.py [--samples N] [--template TEMPLATE_ID]

Requires:
    - Voice dependencies: uv pip install -e '.[voice]'
    - OPENAI_API_KEY environment variable
    - LibriSpeech samples: make download-test-audio
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from clanker.models import Context, Persona
from clanker.providers.openai.llm import OpenAILLM
from clanker.providers.openai.stt import OpenAISTT
from clanker.shitposts import (
    ShitpostContext,
    load_meme_templates,
    render_meme_text,
    sample_meme_template,
)
from clanker.voice.vad import SileroVAD
from clanker.voice.worker import AudioBuffer, transcript_loop_once

# Add tests to path for meme_scoring
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
from meme_scoring import MemeScore, score_meme, validate_meme_structure


def get_test_data_dir() -> Path:
    return Path(__file__).parent.parent / "tests" / "data"


def load_librispeech_samples() -> list[dict]:
    """Load LibriSpeech sample metadata."""
    metadata_path = get_test_data_dir() / "librispeech" / "metadata.json"
    if not metadata_path.exists():
        return []
    with metadata_path.open() as f:
        metadata = json.load(f)
    return metadata.get("samples", [])


def print_header(title: str) -> None:
    """Print a section header."""
    width = 70
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def print_subheader(title: str) -> None:
    """Print a subsection header."""
    print()
    print(f"--- {title} ---")


def print_score_bar(label: str, score: int, max_score: int = 5) -> None:
    """Print a visual score bar."""
    filled = "█" * score
    empty = "░" * (max_score - score)
    print(f"  {label:12} [{filled}{empty}] {score}/{max_score}")


def format_meme_lines(lines: list[str], indent: int = 4) -> str:
    """Format meme lines for display."""
    prefix = " " * indent
    return "\n".join(f'{prefix}"{line}"' for line in lines)


async def run_pipeline(
    sample: dict,
    llm: OpenAILLM,
    stt: OpenAISTT,
    detector: SileroVAD,
    template_id: str | None,
) -> dict:
    """Run the full pipeline on a single sample."""
    sample_id = sample["id"]
    sample_path = get_test_data_dir() / "librispeech" / f"{sample_id}.pcm"
    sample_rate = sample["sample_rate"]
    expected_text = sample.get("text", "")

    # Read audio
    with sample_path.open("rb") as f:
        pcm_bytes = f.read()

    # 1. Transcribe
    buffers = {1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime.now())}
    events = await transcript_loop_once(
        buffers, stt, sample_rate, detector=detector, max_silence_ms=500
    )

    if not events:
        return {"error": "No transcript events", "sample_id": sample_id}

    transcript_text = " ".join(e.text for e in events)

    # 2. Build context
    shitpost_context = ShitpostContext(
        transcript_utterances=tuple(events),
        channel_type="voice",
    )

    # 3. Select template
    templates = load_meme_templates()
    meme_template = sample_meme_template(templates, template_id=template_id)

    # 4. Generate meme
    context = Context(
        request_id=f"pipeline-{sample_id}",
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

    lines = await render_meme_text(context, llm, meme_template, shitpost_context)

    # 5. Validate structure
    is_valid, validation_error = validate_meme_structure(lines, meme_template)

    # 6. Score quality
    input_context = shitpost_context.get_prompt_input()
    score = await score_meme(llm, meme_template, input_context, lines)

    return {
        "sample_id": sample_id,
        "expected_text": expected_text,
        "transcript": transcript_text,
        "template_id": meme_template.template_id,
        "template_description": meme_template.variant_description or meme_template.variant,
        "meme_lines": lines,
        "is_valid": is_valid,
        "validation_error": validation_error,
        "score": score,
    }


def print_result(result: dict) -> None:
    """Print a single pipeline result."""
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return

    print_subheader(f"Sample: {result['sample_id']}")

    print("\n  Input:")
    print(f"    Expected: {result['expected_text'][:80]}...")
    print(f"    Transcript: {result['transcript'][:80]}...")

    print(f"\n  Template: {result['template_id']}")
    print(f"    Description: {result['template_description']}")

    print("\n  Generated Meme:")
    print(format_meme_lines(result["meme_lines"]))

    if not result["is_valid"]:
        print(f"\n  ⚠️  Validation Error: {result['validation_error']}")

    score: MemeScore = result["score"]
    print("\n  Quality Scores:")
    print_score_bar("Relevance", score.relevance)
    print_score_bar("Format", score.format_adherence)
    print_score_bar("Coherence", score.coherence)
    print(f"  {'─' * 30}")
    print(f"  Average:      {score.average:.2f}/5.00  {'✓ PASS' if score.passes_threshold else '✗ FAIL'}")

    print(f"\n  Reasoning: {score.reasoning}")


def print_summary(results: list[dict]) -> None:
    """Print aggregate summary statistics."""
    print_header("Summary")

    valid_results = [r for r in results if "error" not in r]
    error_results = [r for r in results if "error" in r]

    if error_results:
        print(f"\n  Errors: {len(error_results)}")
        for r in error_results:
            print(f"    - {r['sample_id']}: {r['error']}")

    if not valid_results:
        print("\n  No valid results to summarize.")
        return

    # Aggregate scores
    avg_relevance = sum(r["score"].relevance for r in valid_results) / len(valid_results)
    avg_format = sum(r["score"].format_adherence for r in valid_results) / len(valid_results)
    avg_coherence = sum(r["score"].coherence for r in valid_results) / len(valid_results)
    avg_overall = sum(r["score"].average for r in valid_results) / len(valid_results)

    passing = sum(1 for r in valid_results if r["score"].passes_threshold)
    pass_rate = passing / len(valid_results) * 100

    valid_structure = sum(1 for r in valid_results if r["is_valid"])
    structure_rate = valid_structure / len(valid_results) * 100

    print(f"\n  Samples processed: {len(valid_results)}")
    print(f"  Structure validity: {valid_structure}/{len(valid_results)} ({structure_rate:.0f}%)")
    print(f"  Quality pass rate:  {passing}/{len(valid_results)} ({pass_rate:.0f}%)")

    print("\n  Average Scores:")
    print(f"    Relevance:  {avg_relevance:.2f}/5.00")
    print(f"    Format:     {avg_format:.2f}/5.00")
    print(f"    Coherence:  {avg_coherence:.2f}/5.00")
    print(f"    Overall:    {avg_overall:.2f}/5.00")

    # Template distribution
    templates_used = {}
    for r in valid_results:
        tid = r["template_id"]
        templates_used[tid] = templates_used.get(tid, 0) + 1

    print("\n  Templates used:")
    for tid, count in sorted(templates_used.items(), key=lambda x: -x[1]):
        print(f"    {tid}: {count}")


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test meme generation pipeline with real audio"
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=3,
        help="Number of samples to process (default: 3)",
    )
    parser.add_argument(
        "--template",
        type=str,
        default=None,
        help="Specific template ID to use (default: random)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    # Check API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable required")
        return 1

    # Load samples
    samples = load_librispeech_samples()
    if not samples:
        print("ERROR: No LibriSpeech samples found. Run: make download-test-audio")
        return 1

    samples = samples[: args.samples]

    if not args.json:
        print_header("Meme Generation Pipeline Test")
        print(f"\n  Samples: {len(samples)}")
        print(f"  Template: {args.template or 'random'}")

    # Initialize components
    detector = SileroVAD(warmup=True)
    stt = OpenAISTT(api_key=api_key)
    llm = OpenAILLM(api_key=api_key)

    # Process samples
    results = []
    for sample in samples:
        try:
            result = await run_pipeline(sample, llm, stt, detector, args.template)
            results.append(result)
            if not args.json:
                print_result(result)
        except Exception as e:
            results.append({"error": str(e), "sample_id": sample["id"]})
            if not args.json:
                print(f"\n  ERROR processing {sample['id']}: {e}")

    if args.json:
        # JSON output
        json_results = []
        for r in results:
            if "error" in r:
                json_results.append(r)
            else:
                json_results.append({
                    "sample_id": r["sample_id"],
                    "transcript": r["transcript"],
                    "template_id": r["template_id"],
                    "meme_lines": r["meme_lines"],
                    "is_valid": r["is_valid"],
                    "scores": {
                        "relevance": r["score"].relevance,
                        "format": r["score"].format_adherence,
                        "coherence": r["score"].coherence,
                        "average": r["score"].average,
                        "passes": r["score"].passes_threshold,
                    },
                    "reasoning": r["score"].reasoning,
                })
        print(json.dumps(json_results, indent=2))
    else:
        print_summary(results)

    # Return non-zero if any failures
    has_failures = any(
        "error" in r or not r.get("score", MemeScore(1, 1, 1, "", "")).passes_threshold
        for r in results
    )
    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
