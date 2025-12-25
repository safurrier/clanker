#!/usr/bin/env python3
"""Test the audio capture pipeline with real audio samples.

This script runs the full pipeline on LibriSpeech and AMI samples,
reporting detailed metrics on VAD detection and transcription accuracy.

Usage:
    python scripts/test_audio_pipeline.py [--librispeech] [--ami] [--stt]

Requires voice dependencies: uv pip install -e '.[voice]'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from clanker.providers.openai.stt import OpenAISTT
from clanker.voice.chunker import AudioChunk
from clanker.voice.vad import EnergyVAD, SileroVAD
from clanker.voice.worker import AudioBuffer, _slice_pcm, transcript_loop_once


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


def load_ami_samples() -> dict:
    """Load AMI sample metadata."""
    metadata_path = get_test_data_dir() / "ami" / "metadata.json"
    if not metadata_path.exists():
        return {}
    with metadata_path.open() as f:
        return json.load(f)


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def calculate_wer(reference: str, hypothesis: str) -> dict:
    """Calculate Word Error Rate with details."""
    ref_words = normalize_text(reference).split()
    hyp_words = normalize_text(hypothesis).split()

    if not ref_words:
        return {
            "wer": 0.0 if not hyp_words else float(len(hyp_words)),
            "ref_words": 0,
            "hyp_words": len(hyp_words),
        }

    # Levenshtein distance
    m, n = len(ref_words), len(hyp_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j - 1], dp[i][j - 1], dp[i - 1][j])

    distance = dp[m][n]
    return {
        "wer": distance / len(ref_words),
        "distance": distance,
        "ref_words": len(ref_words),
        "hyp_words": len(hyp_words),
    }


def test_librispeech_vad() -> None:
    """Test VAD detection on LibriSpeech samples."""
    print("\n" + "=" * 70)
    print("LIBRISPEECH VAD DETECTION TEST")
    print("=" * 70)

    samples = load_librispeech_samples()
    if not samples:
        print("⚠️  No LibriSpeech samples found. Run: make download-test-audio")
        return

    librispeech_dir = get_test_data_dir() / "librispeech"

    # Initialize VADs
    print("\n🔧 Initializing Silero VAD (ML-based)...")
    silero_vad = SileroVAD(warmup=True)
    energy_vad = EnergyVAD(threshold=500, padding_ms=100)

    print(f"\n📊 Testing {len(samples)} samples:\n")

    for sample in samples:
        pcm_path = librispeech_dir / sample["pcm_file"]
        if not pcm_path.exists():
            print(f"  ⚠️  Missing: {sample['pcm_file']}")
            continue

        with pcm_path.open("rb") as f:
            pcm_bytes = f.read()

        sample_rate = sample.get("sample_rate", 16000)
        audio_duration_ms = len(pcm_bytes) / 2 / sample_rate * 1000

        print(f"  📁 {sample['id']}")
        print(f"     Duration: {audio_duration_ms:.0f}ms ({audio_duration_ms/1000:.1f}s)")
        print(f"     Ground truth: \"{sample['transcript'][:60]}...\"")

        # Test Silero VAD
        silero_segments = silero_vad.detect(pcm_bytes, sample_rate)
        silero_speech_ms = sum(s.end_ms - s.start_ms for s in silero_segments)
        silero_ratio = silero_speech_ms / audio_duration_ms if audio_duration_ms > 0 else 0

        print("\n     🤖 Silero VAD:")
        print(f"        Segments: {len(silero_segments)}")
        print(f"        Speech detected: {silero_speech_ms:.0f}ms ({silero_ratio:.1%})")
        if silero_segments:
            print(
                f"        First segment: {silero_segments[0].start_ms}ms - {silero_segments[0].end_ms}ms"
            )
            print(
                f"        Last segment: {silero_segments[-1].start_ms}ms - {silero_segments[-1].end_ms}ms"
            )

        # Test Energy VAD
        energy_segments = energy_vad.detect(pcm_bytes, sample_rate)
        energy_speech_ms = sum(s.end_ms - s.start_ms for s in energy_segments)
        energy_ratio = energy_speech_ms / audio_duration_ms if audio_duration_ms > 0 else 0

        print("\n     ⚡ Energy VAD:")
        print(f"        Segments: {len(energy_segments)}")
        print(f"        Speech detected: {energy_speech_ms:.0f}ms ({energy_ratio:.1%})")

        print()


async def test_librispeech_stt() -> None:
    """Test full STT pipeline on LibriSpeech samples."""
    print("\n" + "=" * 70)
    print("LIBRISPEECH FULL TRANSCRIPTION TEST (OpenAI Whisper)")
    print("=" * 70)

    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY not set. Skipping STT test.")
        return

    samples = load_librispeech_samples()
    if not samples:
        print("⚠️  No LibriSpeech samples found.")
        return

    librispeech_dir = get_test_data_dir() / "librispeech"

    print("\n🔧 Initializing pipeline...")
    detector = SileroVAD(warmup=True)
    stt = OpenAISTT(api_key=os.environ["OPENAI_API_KEY"])

    print(f"\n📊 Transcribing {len(samples)} samples:\n")

    results = []
    for sample in samples:
        pcm_path = librispeech_dir / sample["pcm_file"]
        if not pcm_path.exists():
            continue

        with pcm_path.open("rb") as f:
            pcm_bytes = f.read()

        sample_rate = sample.get("sample_rate", 16000)
        ground_truth = sample["transcript"]

        print(f"  📁 {sample['id']}")
        print(f"     Ground truth: \"{ground_truth}\"")

        # Run through pipeline
        buffers = {1: AudioBuffer(pcm_bytes=pcm_bytes, start_time=datetime.now())}

        events = await transcript_loop_once(
            buffers, stt, sample_rate, detector=detector, max_silence_ms=500
        )

        hypothesis = " ".join(e.text for e in events)
        print(f"     Transcribed:  \"{hypothesis}\"")

        # Calculate WER
        wer_result = calculate_wer(ground_truth, hypothesis)
        print("\n     📈 Metrics:")
        print(f"        Events: {len(events)}")
        print(f"        WER: {wer_result['wer']:.2%}")
        print(f"        Edit distance: {wer_result['distance']} / {wer_result['ref_words']} words")

        results.append({
            "sample_id": sample["id"],
            "ground_truth": ground_truth,
            "hypothesis": hypothesis,
            "wer": wer_result["wer"],
            "events": len(events),
        })

        print()

    if results:
        print("\n" + "-" * 70)
        print("SUMMARY")
        print("-" * 70)
        avg_wer = sum(r["wer"] for r in results) / len(results)
        print(f"  Samples tested: {len(results)}")
        print(f"  Average WER: {avg_wer:.2%}")
        print(f"  Best WER: {min(r['wer'] for r in results):.2%}")
        print(f"  Worst WER: {max(r['wer'] for r in results):.2%}")

        if avg_wer < 0.05:
            print("\n  ✅ EXCELLENT - WER under 5%")
        elif avg_wer < 0.10:
            print("\n  ✅ GOOD - WER under 10%")
        else:
            print("\n  ⚠️  WER above 10% - may need investigation")


def test_ami_vad() -> None:
    """Test VAD detection on AMI multi-speaker samples."""
    print("\n" + "=" * 70)
    print("AMI CORPUS MULTI-SPEAKER VAD TEST")
    print("=" * 70)

    ami_data = load_ami_samples()
    if not ami_data or not ami_data.get("speakers"):
        print("⚠️  No AMI samples found. Run: make download-test-audio")
        return

    ami_dir = get_test_data_dir() / "ami"

    print("\n🔧 Initializing Silero VAD...")
    detector = SileroVAD(warmup=True)

    print(f"\n📊 Testing {len(ami_data['speakers'])} speakers:\n")

    for speaker_meta in ami_data["speakers"]:
        pcm_path = ami_dir / speaker_meta["pcm_file"]
        if not pcm_path.exists():
            print(f"  ⚠️  Missing: {speaker_meta['pcm_file']}")
            continue

        with pcm_path.open("rb") as f:
            pcm_bytes = f.read()

        sample_rate = speaker_meta.get("sample_rate", 16000)
        audio_duration_ms = len(pcm_bytes) / 2 / sample_rate * 1000

        print(f"  👤 Speaker {speaker_meta['speaker']}")
        print(f"     File: {speaker_meta['pcm_file']}")
        print(f"     Duration: {audio_duration_ms:.0f}ms ({audio_duration_ms/1000:.1f}s)")

        segments = detector.detect(pcm_bytes, sample_rate)
        speech_ms = sum(s.end_ms - s.start_ms for s in segments)
        speech_ratio = speech_ms / audio_duration_ms if audio_duration_ms > 0 else 0

        print(f"     Segments: {len(segments)}")
        print(f"     Speech detected: {speech_ms:.0f}ms ({speech_ratio:.1%})")

        if segments:
            # Show first few segments
            print("     Sample segments:")
            for seg in segments[:5]:
                print(f"       - {seg.start_ms}ms to {seg.end_ms}ms ({seg.end_ms - seg.start_ms}ms)")
            if len(segments) > 5:
                print(f"       ... and {len(segments) - 5} more")

        print()


async def test_ami_stt() -> None:
    """Test full STT pipeline on AMI multi-speaker samples.

    Uses a subset (first 60 seconds) to keep API costs reasonable
    and filters out segments < 200ms (OpenAI minimum is 100ms).
    """
    print("\n" + "=" * 70)
    print("AMI CORPUS MULTI-SPEAKER TRANSCRIPTION TEST")
    print("=" * 70)

    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY not set. Skipping STT test.")
        return

    ami_data = load_ami_samples()
    if not ami_data or not ami_data.get("speakers"):
        print("⚠️  No AMI samples found.")
        return

    ami_dir = get_test_data_dir() / "ami"
    sample_rate = ami_data.get("sample_rate", 16000)

    print("\n🔧 Initializing pipeline...")
    detector = SileroVAD(warmup=True)
    stt = OpenAISTT(api_key=os.environ["OPENAI_API_KEY"])

    # Process first 60 seconds of each speaker for cost/speed
    clip_duration_ms = 60000
    min_segment_ms = 750  # Test with 750ms minimum

    print(f"\n📊 Processing first {clip_duration_ms/1000:.0f}s of each speaker...")
    print(f"   (Filtering segments < {min_segment_ms}ms)\n")

    transcripts = []

    for speaker_meta in ami_data["speakers"]:
        pcm_path = ami_dir / speaker_meta["pcm_file"]
        if not pcm_path.exists():
            continue

        with pcm_path.open("rb") as f:
            pcm_bytes = f.read()

        speaker = speaker_meta["speaker"]

        # Clip to first N ms (bytes = ms / 1000 * sample_rate * 2)
        clip_bytes = clip_duration_ms * sample_rate * 2 // 1000
        pcm_clip = pcm_bytes[:clip_bytes]

        # Detect speech segments
        segments = detector.detect(pcm_clip, sample_rate)

        # Filter short segments
        segments = [s for s in segments if (s.end_ms - s.start_ms) >= min_segment_ms]

        print(f"  👤 Speaker {speaker}: {len(segments)} segments >= {min_segment_ms}ms")

        # Transcribe each segment
        for seg in segments[:10]:  # Limit to 10 segments per speaker
            chunk = AudioChunk(start_ms=seg.start_ms, end_ms=seg.end_ms)
            chunk_bytes = _slice_pcm(pcm_clip, sample_rate, chunk)
            text = await stt.transcribe(chunk_bytes)
            duration = seg.end_ms - seg.start_ms
            transcripts.append({
                "speaker": speaker,
                "start_ms": seg.start_ms,
                "end_ms": seg.end_ms,
                "duration_ms": duration,
                "text": text,
            })
            print(
                f"     [{seg.start_ms/1000:.1f}s-{seg.end_ms/1000:.1f}s] ({duration}ms): "
                f"\"{text[:60]}{'...' if len(text) > 60 else ''}\""
            )

    print("\n" + "-" * 70)
    print("SUMMARY")
    print("-" * 70)

    if transcripts:
        print(f"  Total utterances transcribed: {len(transcripts)}")
        print(f"  Average duration: {sum(t['duration_ms'] for t in transcripts) / len(transcripts):.0f}ms")

        by_speaker: dict[str, list[dict]] = {}
        for t in transcripts:
            if t["speaker"] not in by_speaker:
                by_speaker[t["speaker"]] = []
            by_speaker[t["speaker"]].append(t)

        print("\n  By speaker:")
        for spk in sorted(by_speaker.keys()):
            spk_transcripts = by_speaker[spk]
            word_count = sum(len(t["text"].split()) for t in spk_transcripts)
            print(f"    Speaker {spk}: {len(spk_transcripts)} utterances, ~{word_count} words")
    else:
        print("  No transcripts generated")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test audio capture pipeline")
    parser.add_argument("--librispeech", action="store_true", help="Test LibriSpeech samples")
    parser.add_argument("--ami", action="store_true", help="Test AMI samples")
    parser.add_argument("--stt", action="store_true", help="Include STT tests (requires OPENAI_API_KEY)")
    parser.add_argument("--all", action="store_true", help="Run all tests")

    args = parser.parse_args()

    # Default to all if nothing specified
    if not (args.librispeech or args.ami or args.all):
        args.all = True

    print("🎤 Audio Pipeline Test Report")
    print("=" * 70)

    if args.all or args.librispeech:
        test_librispeech_vad()
        if args.stt:
            asyncio.run(test_librispeech_stt())

    if args.all or args.ami:
        test_ami_vad()
        if args.stt:
            asyncio.run(test_ami_stt())

    print("\n✅ Tests complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
