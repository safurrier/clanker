# Voice Pipeline Improvements

## Critical Fixes

### 1. Add torch/numpy as Optional Dependencies

**File:** `pyproject.toml`

Add optional dependency group for voice with Silero support:

```toml
[project.optional-dependencies]
voice = [
    "torch>=2.0.1",
    "numpy>=1.25.0",
]
```

Users install with: `uv pip install -e ".[voice]"`

### 2. Improve Silero VAD Initialization

**File:** `src/clanker/voice/vad.py`

Replace lazy loading with explicit initialization:

```python
class SileroVAD:
    """Silero VAD-based speech detector (requires torch/numpy)."""

    def __init__(self, warmup: bool = True) -> None:
        self._model = None
        self._torch = None
        self._np = None
        if warmup:
            self._load()

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import numpy as np
            import torch
        except ImportError as e:
            raise RuntimeError(
                "Silero VAD requires torch and numpy. "
                "Install with: uv pip install 'clanker9000[voice]'"
            ) from e

        try:
            model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=True,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load Silero VAD model: {e}. "
                "Ensure you have network access or the model is cached."
            ) from e

        self._model = model
        self._torch = torch
        self._np = np
```

### 3. Replace audioop with NumPy

**File:** `src/clanker/voice/vad.py`

Replace deprecated `audioop.rms()` with numpy:

```python
@dataclass(frozen=True)
class EnergyVAD:
    """Energy-based speech detector using RMS thresholding."""

    frame_ms: int = 30
    threshold: int = 500
    padding_ms: int = 300

    def detect(self, pcm_bytes: bytes, sample_rate_hz: int) -> list[SpeechSegment]:
        try:
            import numpy as np
        except ImportError:
            # Fallback to audioop for backwards compatibility
            import audioop
            return self._detect_audioop(pcm_bytes, sample_rate_hz, audioop)

        return self._detect_numpy(pcm_bytes, sample_rate_hz, np)

    def _compute_rms_numpy(self, frame: bytes, np) -> float:
        """Compute RMS using numpy."""
        samples = np.frombuffer(frame, dtype=np.int16)
        return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
```

### 4. Add Model Warmup on Startup

**File:** `src/clanker_bot/voice_ingest.py`

Add warmup function:

```python
async def warmup_silero_vad() -> SpeechDetector | None:
    """Warmup Silero VAD on startup. Returns None if unavailable."""
    try:
        detector = SileroVAD(warmup=True)
        # Test with dummy audio
        dummy_pcm = b"\x00\x00" * 16000  # 1 second of silence
        detector.detect(dummy_pcm, 16000)
        return detector
    except Exception as e:
        logging.warning(f"Silero VAD unavailable, using EnergyVAD: {e}")
        return None
```

**Usage in bot startup:**
```python
@bot.event
async def on_ready():
    global default_detector
    default_detector = await warmup_silero_vad()
    logging.info(f"Voice detector: {type(default_detector).__name__}")
```

### 5. Extract Magic Numbers to Constants

**File:** `src/clanker/voice/vad.py`

```python
# Silero VAD configuration
SILERO_SAMPLE_RATE = 16000
SILERO_WINDOW_SIZE = 512
SILERO_SPEECH_THRESHOLD = 0.4
SILERO_WINDOW_STEP_MS = 100

# EnergyVAD defaults
ENERGY_VAD_FRAME_MS = 30
ENERGY_VAD_THRESHOLD = 500
ENERGY_VAD_PADDING_MS = 300
```

### 6. Add Proper Error Handling

**File:** `src/clanker_bot/voice_ingest.py`

```python
def write(self, user: object, data: object) -> None:
    """Write audio data from a user (called by discord voice_recv)."""
    try:
        if not user or not hasattr(user, "id"):
            return
        if not hasattr(data, "pcm"):
            return

        user_id = getattr(user, "id")
        pcm_data = getattr(data, "pcm")

        if not isinstance(pcm_data, bytes):
            self.logger.warning(f"Invalid PCM data type: {type(pcm_data)}")
            return

        self.worker.add_pcm(user_id, pcm_data)
        if self.worker.should_process():
            task = asyncio.create_task(self._flush())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
    except Exception as e:
        self.logger.error(f"Error processing audio: {e}", exc_info=True)
```

## Dockerfile for Production

Based on the Sparky reference, create `Dockerfile`:

```dockerfile
FROM python:3.11 AS builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Clone Silero VAD model (avoids rate limiting in production)
FROM builder AS silero-vad
RUN git clone https://github.com/snakers4/silero-vad.git /silero-vad && \
    rm -rf /silero-vad/.git

# Main application stage
FROM python:3.11-slim

WORKDIR /app

# Copy application code
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -e ".[voice]"

# Copy pre-downloaded Silero model
COPY --from=silero-vad /silero-vad ./silero-vad

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TORCH_HOME=/app/.cache/torch

# Run the bot
CMD ["python", "-m", "clanker_bot.main"]
```

**Build and run:**
```bash
docker build -t clanker-bot .
docker run -e DISCORD_TOKEN=$DISCORD_TOKEN -e OPENAI_API_KEY=$OPENAI_API_KEY clanker-bot
```

## Testing Improvements

### Add Integration Test for Silero VAD

**File:** `tests/test_silero_vad.py`

```python
"""Tests for Silero VAD integration."""

import pytest
from clanker.voice.vad import SileroVAD, EnergyVAD, resolve_detector


@pytest.mark.network
def test_silero_vad_loads():
    """Test that Silero VAD can be loaded."""
    detector = SileroVAD(warmup=True)
    assert detector._model is not None


@pytest.mark.network
def test_silero_vad_detects_speech():
    """Test that Silero VAD detects speech segments."""
    detector = SileroVAD(warmup=True)
    # Load test audio
    import wave
    with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
        pcm_bytes = wf.readframes(wf.getnframes())
        sample_rate = wf.getframerate()

    segments = detector.detect(pcm_bytes, sample_rate)
    assert len(segments) > 0


def test_resolve_detector_fallback():
    """Test that resolve_detector falls back gracefully."""
    detector = resolve_detector(prefer_silero=True)
    # Should return either SileroVAD or EnergyVAD
    assert isinstance(detector, (SileroVAD, EnergyVAD))
```

## Configuration

### Add Voice Config Section

**File:** `config.yaml`

```yaml
voice:
  # Speech detection
  detector: "silero"  # Options: silero, energy

  # Silero VAD settings
  silero:
    threshold: 0.4
    window_size: 512
    warmup_on_startup: true

  # Energy VAD settings (fallback)
  energy:
    frame_ms: 30
    threshold: 500
    padding_ms: 300

  # Transcription settings
  chunk_seconds: 2.0
  max_silence_ms: 500
  sample_rate_hz: 48000
```

## Priority Order

1. **CRITICAL (Do First)**
   - Add torch/numpy to optional dependencies
   - Fix Silero VAD error handling
   - Add model warmup on startup

2. **HIGH (Do Soon)**
   - Replace audioop with numpy
   - Extract magic numbers
   - Add proper error handling in voice_ingest

3. **MEDIUM (Nice to Have)**
   - Add Dockerfile
   - Add Silero integration tests
   - Add voice configuration section

4. **LOW (Future)**
   - Add metrics/monitoring
   - Add audio quality validation
   - Add configurable VAD parameters
