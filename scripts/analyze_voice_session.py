#!/usr/bin/env python3
"""Analyze voice debug capture sessions.

Usage:
    python scripts/analyze_voice_session.py voice_debug/session_*/
    python scripts/analyze_voice_session.py voice_debug/session_2024-01-15_*/

This script analyzes captured voice pipeline sessions and generates reports
showing potential issues with VAD detection, sample rates, and transcription.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_manifest(session_dir: Path) -> dict | None:
    """Load manifest.json from a session directory."""
    manifest_path = session_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"  ⚠️  No manifest.json in {session_dir}")
        return None
    return json.loads(manifest_path.read_text())


def analyze_session(session_dir: Path) -> dict:
    """Analyze a single debug session and return findings."""
    findings: dict = {
        "session_id": session_dir.name,
        "warnings": [],
        "info": [],
        "stats": {},
    }

    manifest = load_manifest(session_dir)
    if manifest is None:
        findings["warnings"].append("Missing manifest.json")
        return findings

    config = manifest.get("config", {})
    users = manifest.get("users", {})
    stats = manifest.get("stats", {})

    findings["stats"] = stats

    # Check sample rate
    sample_rate = config.get("sample_rate_hz", 0)
    if sample_rate == 48000:
        findings["info"].append(
            f"Sample rate: {sample_rate}Hz (Discord default, will be resampled to 16kHz)"
        )
    elif sample_rate == 16000:
        findings["info"].append(f"Sample rate: {sample_rate}Hz (optimal for Whisper)")
    else:
        findings["warnings"].append(f"Unusual sample rate: {sample_rate}Hz")

    # Check VAD type
    vad_type = config.get("vad_type", "unknown")
    findings["info"].append(f"VAD type: {vad_type}")

    # Analyze per-user data
    for user_id, user_data in users.items():
        raw_duration = user_data.get("raw_buffer_duration_ms", 0)
        vad_segments = user_data.get("vad_segments", [])
        utterances = user_data.get("utterances", [])
        filtered_count = user_data.get("utterances_filtered_count", 0)

        # Calculate VAD coverage
        speech_ms = sum(s["end_ms"] - s["start_ms"] for s in vad_segments)
        if raw_duration > 0:
            coverage = speech_ms / raw_duration
            if coverage < 0.1:
                findings["warnings"].append(
                    f"User {user_id}: Low VAD coverage ({coverage:.1%}) - "
                    "may be missing speech"
                )
            elif coverage > 0.95:
                findings["warnings"].append(
                    f"User {user_id}: Very high VAD coverage ({coverage:.1%}) - "
                    "may include background noise"
                )
            else:
                findings["info"].append(
                    f"User {user_id}: VAD coverage {coverage:.1%} "
                    f"({speech_ms}ms speech / {raw_duration}ms total)"
                )

        # Check for empty transcriptions
        empty_count = sum(1 for u in utterances if not u.get("stt_text", "").strip())
        if empty_count > 0:
            findings["warnings"].append(
                f"User {user_id}: {empty_count} empty transcriptions"
            )

        # Check for very short utterances that got transcribed
        short_transcribed = [
            u for u in utterances if u.get("duration_ms", 0) < 300 and u.get("stt_text")
        ]
        if short_transcribed:
            findings["warnings"].append(
                f"User {user_id}: {len(short_transcribed)} very short utterances "
                "(<300ms) were transcribed - may contain hallucinations"
            )

        # Check STT latency
        latencies = [u.get("stt_latency_ms", 0) for u in utterances]
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            findings["info"].append(
                f"User {user_id}: STT latency avg={avg_latency:.0f}ms max={max_latency:.0f}ms"
            )
            if max_latency > 5000:
                findings["warnings"].append(
                    f"User {user_id}: High STT latency ({max_latency:.0f}ms)"
                )

        # Report filtered utterances
        if filtered_count > 0:
            total_utterances = len(utterances) + filtered_count
            findings["info"].append(
                f"User {user_id}: {filtered_count}/{total_utterances} utterances "
                "filtered (too short)"
            )

    return findings


def print_findings(findings: dict) -> None:
    """Print analysis findings to console."""
    print(f"\n{'=' * 60}")
    print(f"Session: {findings['session_id']}")
    print("=" * 60)

    stats = findings.get("stats", {})
    if stats:
        print(f"\n📊 Stats:")
        print(f"   Total raw audio: {stats.get('total_raw_audio_ms', 0) / 1000:.1f}s")
        print(f"   Speech detected: {stats.get('total_speech_detected_ms', 0) / 1000:.1f}s")
        print(f"   Utterances: {stats.get('total_utterances', 0)}")
        print(f"   Filtered: {stats.get('total_utterances_filtered', 0)}")

    if findings["info"]:
        print(f"\nℹ️  Info:")
        for info in findings["info"]:
            print(f"   • {info}")

    if findings["warnings"]:
        print(f"\n⚠️  Warnings:")
        for warning in findings["warnings"]:
            print(f"   • {warning}")
    else:
        print(f"\n✅ No warnings")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze voice debug capture sessions"
    )
    parser.add_argument(
        "sessions",
        nargs="+",
        type=Path,
        help="Session directories to analyze (supports glob patterns)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of human-readable",
    )

    args = parser.parse_args()

    # Expand any directories that might be glob patterns
    session_dirs: list[Path] = []
    for path in args.sessions:
        if path.is_dir():
            session_dirs.append(path)
        else:
            # Try as glob pattern from current directory
            session_dirs.extend(Path(".").glob(str(path)))

    if not session_dirs:
        print("No session directories found")
        return 1

    print(f"🔍 Analyzing {len(session_dirs)} session(s)...")

    all_findings = []
    for session_dir in sorted(session_dirs):
        findings = analyze_session(session_dir)
        all_findings.append(findings)
        if not args.json:
            print_findings(findings)

    if args.json:
        print(json.dumps(all_findings, indent=2))

    # Summary
    if not args.json and len(session_dirs) > 1:
        total_warnings = sum(len(f["warnings"]) for f in all_findings)
        print(f"\n{'=' * 60}")
        print(f"SUMMARY: {len(session_dirs)} sessions, {total_warnings} warnings")
        print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
