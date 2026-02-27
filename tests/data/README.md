# Test Audio Data

This directory contains audio samples for testing the voice capture and transcription pipeline.

## Directory Structure

```
tests/data/
├── README.md              # This file
├── metadata.json          # Synthetic sample metadata
├── sample*.wav            # Synthetic sine wave samples
├── sample*.pcm            # PCM versions of synthetic samples
├── generate_samples.py    # Script to regenerate synthetic samples
│
├── librispeech/           # LibriSpeech test-clean samples
│   ├── metadata.json      # Sample metadata with transcripts
│   ├── *.flac            # Original FLAC files (gitignored)
│   └── *.pcm             # Converted PCM files (gitignored)
│
└── ami/                   # AMI Corpus meeting samples
    ├── metadata.json      # Speaker metadata with segments
    └── *.pcm             # Speaker audio files (gitignored)
```

## Downloading Real Audio Samples

Audio files are not stored in git due to size. Download them with:

```bash
make download-test-audio
```

Or manually:

```bash
python scripts/download_test_audio.py --all
```

### LibriSpeech

Source: [OpenSLR](https://www.openslr.org/12/)

The download script fetches samples from the `test-clean` subset (346MB total).
We extract 3 short samples (< 10 seconds each) for fast testing.

**Manual download:**
1. Download `test-clean.tar.gz` from https://www.openslr.org/12/
2. Extract to `tests/data/librispeech/`
3. Run `python scripts/download_test_audio.py --extract-librispeech`

### AMI Corpus

Source: [AMI Corpus](https://groups.inf.ed.ac.uk/ami/download/)

The AMI Corpus contains multi-speaker meeting recordings with individual
headset channels per speaker. Full access requires registration.

**Fallback:** If AMI download fails, the script creates synthetic multi-speaker
samples that simulate 4 speakers with different audio patterns.

**Manual download:**
1. Register at https://groups.inf.ed.ac.uk/ami/download/
2. Download ES2002a meeting audio files
3. Place in `tests/data/ami/`

## Running Tests

### Unit Tests (No Downloads Required)

```bash
# Run all non-network tests
make test

# Run only audio scenario tests
uv run pytest tests/test_audio_scenarios.py -v
```

### Network Tests (Requires Downloads + API Key)

```bash
# Download audio first
make download-test-audio

# Set OpenAI API key for Whisper STT
export OPENAI_API_KEY=sk-...

# Run network tests
uv run pytest tests/test_real_audio.py -v -m network
```

### Slow Tests

Some tests are marked `@pytest.mark.slow` for longer-running validation:

```bash
uv run pytest tests/test_real_audio.py -v -m "network and slow"
```

## Test Categories

| Test File | Audio Source | Network Required | Description |
|-----------|--------------|------------------|-------------|
| `test_audio_e2e.py` | Synthetic | No | E2E with sine waves |
| `test_audio_scenarios.py` | Synthetic | No | Behavioral scenarios |
| `test_real_audio.py` | LibriSpeech, AMI | Yes | Real speech accuracy |

## Metrics

The `tests/metrics.py` module provides WER (Word Error Rate) calculation:

```python
from tests.metrics import calculate_wer, calculate_wer_details

wer = calculate_wer("hello world", "hello word")  # 0.5

details = calculate_wer_details("the quick fox", "the slow fox")
# {'wer': 0.333, 'substitutions': 1, 'insertions': 0, 'deletions': 0, ...}
```

## Troubleshooting

### "LibriSpeech samples not downloaded"

Run `make download-test-audio` to download samples.

### "ffmpeg not found"

Install ffmpeg for audio conversion:
- macOS: `brew install ffmpeg`
- Ubuntu: `sudo apt install ffmpeg`

### Silero VAD tests skipped

Silero VAD requires PyTorch. Install with:

```bash
uv pip install -e ".[voice]"
```

### Network tests fail with API error

Ensure `OPENAI_API_KEY` is set and valid.
