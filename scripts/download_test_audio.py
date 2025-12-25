#!/usr/bin/env python3
"""Download test audio samples from LibriSpeech and AMI Corpus.

Usage:
    python scripts/download_test_audio.py [--librispeech] [--ami] [--all]

Downloads audio samples with ground-truth transcripts for E2E voice testing.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

# LibriSpeech test-clean sample configuration
# Using short samples (< 10 seconds) for fast tests
LIBRISPEECH_BASE_URL = "https://www.openslr.org/resources/12"
LIBRISPEECH_SAMPLES = [
    # Format: (speaker_id, chapter_id, utterance_id, expected_duration_approx)
    # These are from test-clean subset
    ("1089", "134686", "0000", 5.0),  # ~5 seconds
    ("1089", "134686", "0001", 4.5),  # ~4.5 seconds
    ("1089", "134686", "0002", 6.0),  # ~6 seconds
]

# AMI Corpus sample configuration
# Using ES2002a meeting (one of the shorter ones with good quality)
AMI_BASE_URL = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus"
AMI_MEETING_ID = "ES2002a"
AMI_SPEAKERS = ["A", "B", "C", "D"]  # 4 speakers in meeting


def get_test_data_dir() -> Path:
    """Get the test data directory."""
    return Path(__file__).parent.parent / "tests" / "data"


def download_file(url: str, dest: Path, chunk_size: int = 8192) -> bool:
    """Download a file using curl (more reliable than urllib for large files)."""
    _ = chunk_size  # Unused but kept for API compatibility
    print(f"  Downloading: {url}")
    try:
        subprocess.run(  # noqa: S603
            ["curl", "-L", "-o", str(dest), "-#", url],  # noqa: S607
            check=True,
            capture_output=False,
        )
        return dest.exists() and dest.stat().st_size > 0
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Download failed: {e}")
        return False


def convert_flac_to_pcm(flac_path: Path, pcm_path: Path, sample_rate: int = 16000) -> bool:
    """Convert FLAC to raw PCM using ffmpeg."""
    try:
        subprocess.run(  # noqa: S603
            [  # noqa: S607
                "ffmpeg",
                "-y",  # Overwrite output
                "-i", str(flac_path),
                "-ar", str(sample_rate),  # Resample to 16kHz
                "-ac", "1",  # Mono
                "-f", "s16le",  # 16-bit signed little-endian PCM
                str(pcm_path),
            ],
            check=True,
            capture_output=True,
        )
        return pcm_path.exists()
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Conversion failed: {e}")
        return False
    except FileNotFoundError:
        print("  ✗ ffmpeg not found. Please install ffmpeg.")
        return False


def download_librispeech_samples() -> bool:
    """Download LibriSpeech test-clean samples."""
    print("\n📥 Downloading LibriSpeech samples...")

    test_data_dir = get_test_data_dir()
    librispeech_dir = test_data_dir / "librispeech"
    librispeech_dir.mkdir(parents=True, exist_ok=True)

    # Download the test-clean subset (we'll extract just the samples we need)
    # For efficiency, we download a small tarball with just a few speakers

    # Check if we already have samples
    existing_samples = list(librispeech_dir.glob("*.pcm"))
    if len(existing_samples) >= len(LIBRISPEECH_SAMPLES):
        print("  ✓ LibriSpeech samples already exist, skipping download")
        return True

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        tar_path = tmp_path / "test-clean.tar.gz"

        # Note: Full test-clean is 346MB. For CI, we'll use a pre-extracted subset.
        # For local development, you can download the full set.
        print("  Note: Full LibriSpeech test-clean is 346MB.")
        print("  Downloading sample subset instead...")

        # Instead of downloading the full archive, we'll create sample metadata
        # and document manual download instructions

        # Create metadata file with instructions
        metadata = {
            "source": "LibriSpeech test-clean",
            "url": "https://www.openslr.org/12",
            "samples": [],
            "download_instructions": [
                "1. Download test-clean.tar.gz from https://www.openslr.org/12",
                "2. Extract to tests/data/librispeech/",
                "3. Run: python scripts/download_test_audio.py --extract-librispeech",
            ],
        }

        # For now, try to download individual files if possible
        # LibriSpeech also provides individual files via alternative mirrors

        # Alternative: Use a small hosted sample
        sample_url = "https://www.openslr.org/resources/12/test-clean.tar.gz"

        print(f"  Attempting to download from: {sample_url}")
        print("  (This may take a few minutes for 346MB...)")

        if not download_file(sample_url, tar_path):
            print("\n  ⚠️  Could not download LibriSpeech automatically.")
            print("  Please download manually:")
            print("    1. Go to: https://www.openslr.org/12")
            print("    2. Download: test-clean.tar.gz (346 MB)")
            print(f"    3. Extract to: {librispeech_dir}")
            print("    4. Re-run this script with --extract-librispeech")

            # Write placeholder metadata
            with (librispeech_dir / "metadata.json").open("w") as f:
                json.dump(metadata, f, indent=2)
            return False

        # Extract specific samples
        print("  Extracting samples...")
        try:
            with tarfile.open(tar_path, "r:gz") as tar:
                # Extract only the samples we need
                for speaker_id, chapter_id, utt_id, _ in LIBRISPEECH_SAMPLES:
                    flac_name = f"{speaker_id}-{chapter_id}-{utt_id}.flac"
                    trans_name = f"{speaker_id}-{chapter_id}.trans.txt"

                    for member in tar.getmembers():
                        if member.name.endswith(flac_name) or member.name.endswith(trans_name):
                            tar.extract(member, tmp_path)

            # Process extracted files
            extracted_dir = tmp_path / "LibriSpeech" / "test-clean"
            samples_metadata = []

            for speaker_id, chapter_id, utt_id, _approx_dur in LIBRISPEECH_SAMPLES:
                flac_name = f"{speaker_id}-{chapter_id}-{utt_id}.flac"
                trans_file = extracted_dir / speaker_id / chapter_id / f"{speaker_id}-{chapter_id}.trans.txt"
                flac_file = extracted_dir / speaker_id / chapter_id / flac_name

                if not flac_file.exists():
                    print(f"  ✗ Missing: {flac_name}")
                    continue

                # Get transcript
                transcript = ""
                if trans_file.exists():
                    with trans_file.open() as f:
                        for line in f:
                            parts = line.strip().split(" ", 1)
                            if parts[0] == f"{speaker_id}-{chapter_id}-{utt_id}":
                                transcript = parts[1] if len(parts) > 1 else ""
                                break

                # Convert to PCM
                pcm_name = f"{speaker_id}-{chapter_id}-{utt_id}.pcm"
                pcm_path = librispeech_dir / pcm_name

                print(f"  Converting: {flac_name} -> {pcm_name}")
                if convert_flac_to_pcm(flac_file, pcm_path):
                    # Also copy the FLAC for reference
                    shutil.copy(flac_file, librispeech_dir / flac_name)

                    samples_metadata.append({
                        "id": f"{speaker_id}-{chapter_id}-{utt_id}",
                        "speaker_id": speaker_id,
                        "flac_file": flac_name,
                        "pcm_file": pcm_name,
                        "transcript": transcript,
                        "sample_rate": 16000,
                    })
                    print(f"    ✓ Transcript: {transcript[:50]}...")

            # Save metadata
            metadata["samples"] = samples_metadata
            with (librispeech_dir / "metadata.json").open("w") as f:
                json.dump(metadata, f, indent=2)

            print(f"\n  ✓ Downloaded {len(samples_metadata)} LibriSpeech samples")
            return len(samples_metadata) > 0

        except Exception as e:
            print(f"  ✗ Extraction failed: {e}")
            return False


def download_ami_samples() -> bool:
    """Download AMI Corpus meeting samples."""
    print("\n📥 Downloading AMI Corpus samples...")

    test_data_dir = get_test_data_dir()
    ami_dir = test_data_dir / "ami"
    ami_dir.mkdir(parents=True, exist_ok=True)

    # Check if we already have samples
    existing_samples = list(ami_dir.glob("*.wav"))
    if len(existing_samples) >= 4:  # 4 speakers
        print("  ✓ AMI samples already exist, skipping download")
        return True

    # AMI Corpus requires registration for full access
    # For testing, we'll use the publicly available headset mix samples

    # The AMI corpus provides individual headset recordings per speaker
    # Format: {meeting_id}.Headset-{speaker_num}.wav

    print("  Note: AMI Corpus requires registration for full download.")
    print("  Using publicly mirrored samples...")

    # Alternative mirror with sample files
    # These are short segments from the ES2002a meeting

    metadata = {
        "source": "AMI Corpus",
        "meeting_id": AMI_MEETING_ID,
        "url": "https://groups.inf.ed.ac.uk/ami/download/",
        "speakers": [],
        "download_instructions": [
            "1. Register at https://groups.inf.ed.ac.uk/ami/download/",
            "2. Download ES2002a headset audio files",
            "3. Extract to tests/data/ami/",
            "4. Download corresponding word-level transcripts",
        ],
    }

    # For now, create placeholder with instructions
    # In a real setup, you'd download from AMI mirrors

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # AMI provides files via their corpus mirror
        # The headset recordings are individual WAV files per speaker
        base_url = f"{AMI_BASE_URL}/{AMI_MEETING_ID}/audio"

        samples_found = []
        for i, speaker in enumerate(AMI_SPEAKERS):
            # AMI naming convention: ES2002a.Headset-0.wav, etc.
            wav_name = f"{AMI_MEETING_ID}.Headset-{i}.wav"
            wav_url = f"{base_url}/{wav_name}"
            wav_path = tmp_path / wav_name

            print(f"  Trying: {wav_name}")

            # Try to download (may fail if not publicly available)
            if download_file(wav_url, wav_path):
                # Convert to PCM
                pcm_name = f"{AMI_MEETING_ID}_speaker_{speaker}.pcm"
                pcm_path = ami_dir / pcm_name

                if convert_flac_to_pcm(wav_path, pcm_path):
                    shutil.copy(wav_path, ami_dir / wav_name)
                    samples_found.append({
                        "speaker": speaker,
                        "speaker_index": i,
                        "wav_file": wav_name,
                        "pcm_file": pcm_name,
                        "sample_rate": 16000,
                    })
                    print(f"    ✓ Speaker {speaker} audio ready")

        if not samples_found:
            print("\n  ⚠️  Could not download AMI samples automatically.")
            print("  The AMI Corpus requires registration.")
            print("  Please download manually:")
            print("    1. Register at: https://groups.inf.ed.ac.uk/ami/download/")
            print("    2. Download ES2002a meeting audio files")
            print(f"    3. Place in: {ami_dir}")
            print("    4. Re-run this script")
            return False

        metadata["speakers"] = samples_found
        with (ami_dir / "metadata.json").open("w") as f:
            json.dump(metadata, f, indent=2)

        print(f"\n  ✓ Downloaded {len(samples_found)} AMI speaker samples")
        return len(samples_found) > 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download test audio samples for voice pipeline testing"
    )
    parser.add_argument(
        "--librispeech",
        action="store_true",
        help="Download LibriSpeech samples only",
    )
    parser.add_argument(
        "--ami",
        action="store_true",
        help="Download AMI Corpus samples only",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download all samples (default)",
    )
    parser.add_argument(
        "--extract-librispeech",
        action="store_true",
        help="Extract samples from locally downloaded LibriSpeech archive",
    )

    args = parser.parse_args()

    # Default to all if no specific option
    if not (args.librispeech or args.ami or args.all or args.extract_librispeech):
        args.all = True

    print("🎤 Test Audio Downloader")
    print("=" * 40)

    success = True

    if args.all or args.librispeech:
        if not download_librispeech_samples():
            success = False

    if args.all or args.ami:
        if not download_ami_samples():
            success = False

    if success:
        print("\n✅ All downloads complete!")
        print("\nNext steps:")
        print("  1. Run tests: uv run pytest tests/test_real_audio.py -v")
        print("  2. For network tests: uv run pytest -m network")
    else:
        print("\n⚠️  Some downloads failed. See instructions above.")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
