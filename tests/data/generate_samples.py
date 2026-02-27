"""Generate test audio samples with known transcripts."""

import json
import struct
import wave
from pathlib import Path

import numpy as np


def generate_sine_wave(
    frequency: float, duration_sec: float, sample_rate: int = 16000
) -> np.ndarray:
    """Generate a sine wave to simulate speech."""
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec))
    # Add some harmonics to make it more speech-like
    signal = (
        np.sin(2 * np.pi * frequency * t) * 0.3
        + np.sin(2 * np.pi * frequency * 2 * t) * 0.2
        + np.sin(2 * np.pi * frequency * 3 * t) * 0.1
    )
    # Add some noise
    signal += np.random.normal(0, 0.05, signal.shape)
    # Normalize
    signal = signal / np.max(np.abs(signal)) * 0.8
    return signal


def save_wav(filename: Path, audio: np.ndarray, sample_rate: int = 16000) -> None:
    """Save audio as WAV file."""
    # Convert to 16-bit PCM
    audio_int16 = (audio * 32767).astype(np.int16)

    with wave.open(str(filename), "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())


def save_pcm(filename: Path, audio: np.ndarray) -> None:
    """Save audio as raw PCM (16-bit signed)."""
    audio_int16 = (audio * 32767).astype(np.int16)
    with open(filename, "wb") as f:
        f.write(audio_int16.tobytes())


def generate_test_samples() -> None:
    """Generate test audio samples with transcripts."""
    data_dir = Path(__file__).parent

    # Sample 1: Short monologue (5 seconds)
    print("Generating sample 1: short monologue...")
    audio1 = generate_sine_wave(200, 5.0)
    save_wav(data_dir / "sample1_monologue.wav", audio1)
    save_pcm(data_dir / "sample1_monologue.pcm", audio1)

    metadata1 = {
        "filename": "sample1_monologue.wav",
        "duration_sec": 5.0,
        "sample_rate": 16000,
        "transcript": "This is a test of the audio transcription system.",
        "description": "5 second monologue, single speaker",
    }

    # Sample 2: Two utterances with pause (8 seconds)
    print("Generating sample 2: two utterances with pause...")
    utterance1 = generate_sine_wave(180, 2.5)
    silence = np.zeros(int(16000 * 1.0))  # 1 second silence
    utterance2 = generate_sine_wave(220, 3.0)
    audio2 = np.concatenate([utterance1, silence, utterance2])
    save_wav(data_dir / "sample2_paused.wav", audio2)
    save_pcm(data_dir / "sample2_paused.pcm", audio2)

    metadata2 = {
        "filename": "sample2_paused.wav",
        "duration_sec": 6.5,
        "sample_rate": 16000,
        "transcript": "First utterance. Second utterance after pause.",
        "utterances": [
            {"start_sec": 0.0, "end_sec": 2.5, "text": "First utterance."},
            {"start_sec": 3.5, "end_sec": 6.5, "text": "Second utterance after pause."},
        ],
        "description": "Two utterances separated by 1 second silence",
    }

    # Sample 3: Simulated multi-speaker (6 seconds)
    print("Generating sample 3: multi-speaker simulation...")
    speaker1_seg1 = generate_sine_wave(190, 1.5)
    gap1 = np.zeros(int(16000 * 0.3))
    speaker2_seg1 = generate_sine_wave(250, 1.2)
    gap2 = np.zeros(int(16000 * 0.3))
    speaker1_seg2 = generate_sine_wave(190, 1.5)
    audio3 = np.concatenate([speaker1_seg1, gap1, speaker2_seg1, gap2, speaker1_seg2])
    save_wav(data_dir / "sample3_multispeaker.wav", audio3)
    save_pcm(data_dir / "sample3_multispeaker.pcm", audio3)

    metadata3 = {
        "filename": "sample3_multispeaker.wav",
        "duration_sec": 5.8,
        "sample_rate": 16000,
        "transcript": "Hello there. How are you? I am doing well.",
        "speakers": [
            {"id": 1, "frequency": 190, "segments": [[0.0, 1.5], [3.0, 4.5]]},
            {"id": 2, "frequency": 250, "segments": [[1.8, 3.0]]},
        ],
        "description": "Two speakers alternating, simulated by different frequencies",
    }

    # Save metadata
    metadata = {
        "samples": [metadata1, metadata2, metadata3],
        "total_duration_sec": 17.3,
        "generated_by": "tests/data/generate_samples.py",
    }

    with open(data_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"✓ Generated 3 samples ({metadata['total_duration_sec']} seconds total)")
    print(f"  - {data_dir / 'sample1_monologue.wav'}")
    print(f"  - {data_dir / 'sample2_paused.wav'}")
    print(f"  - {data_dir / 'sample3_multispeaker.wav'}")
    print(f"  - {data_dir / 'metadata.json'}")


if __name__ == "__main__":
    generate_test_samples()
