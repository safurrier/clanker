# Voice Pipeline

End-to-end documentation of the voice processing system, from Discord audio capture to transcription output.

## Overview

The voice pipeline spans two layers:

1. **SDK Layer** (`src/clanker/voice/`) — Discord-independent audio processing
2. **Discord Layer** (`src/clanker_bot/voice_ingest.py`) — Discord audio capture and bridging

```
Discord Voice Channel
    │
    ▼
┌──────────────────────────────────────┐
│ Discord Layer (clanker_bot)          │
│                                      │
│ voice_ingest.py                      │
│  ├─ VoiceIngestSink (voice_recv)     │
│  ├─ stereo→mono + resample           │
│  └─ AudioBuffer per user             │
│                                      │
│ voice_resilience.py                  │
│  └─ VoiceKeepalive (heartbeat)       │
└──────────────┬───────────────────────┘
               │ mono 16kHz PCM
               ▼
┌──────────────────────────────────────┐
│ SDK Layer (clanker/voice)            │
│                                      │
│ vad.py                               │
│  └─ detect_speech_segments()         │
│     → list[SpeechSegment]            │
│                                      │
│ chunker.py                           │
│  └─ chunk_segments()                 │
│     → list[AudioChunk]              │
│                                      │
│ worker.py                            │
│  └─ transcript_loop_once()           │
│     → list[TranscriptEvent]          │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ Provider Layer                       │
│ providers/openai/stt.py              │
│  └─ OpenAISTT.transcribe()          │
│     (expects WAV-formatted bytes)    │
└──────────────────────────────────────┘
```

## Audio Formats

| Format | Sample Rate | Channels | Bit Depth | Context |
|--------|------------|----------|-----------|---------|
| `DISCORD_FORMAT` | 48000 Hz | 2 (stereo) | 16-bit | Raw from discord-ext-voice-recv |
| `SDK_FORMAT` | 16000 Hz | 1 (mono) | 16-bit | Internal processing |
| `WHISPER_FORMAT` | 16000 Hz | 1 (mono) | 16-bit | OpenAI Whisper input |

Conversion utilities in `src/clanker/providers/audio_utils.py`:
- `stereo_to_mono(pcm_bytes)` — average L/R channels
- `convert_pcm(data, from_format, to_format)` — full format conversion
- `resample_pcm(data, from_rate, to_rate)` — sample rate conversion

## VAD (Voice Activity Detection)

### SileroVAD (default)
- Uses Silero's pre-trained ONNX model via PyTorch
- Processes 512-sample frames (32ms at 16kHz)
- High accuracy, handles background noise well
- Requires `torch` and `numpy` (optional `[voice]` dependency, ~500MB)
- Pre-load with `warmup_voice_detector()` to avoid cold-start latency

### EnergyVAD (fallback)
- Simple RMS energy threshold
- Zero extra dependencies
- Works for clear speech in quiet environments
- Falls back automatically when torch is unavailable

### Key API
```python
from clanker.voice.vad import detect_speech_segments, resolve_detector, EnergyVAD

# Auto-select best available
detector = resolve_detector(prefer_silero=True)

# Or explicitly use energy
detector = EnergyVAD()

# Detect speech
segments = detect_speech_segments(pcm_bytes, sample_rate=16000, detector=detector)
# Returns: list[SpeechSegment(start_ms, end_ms)]
```

## Chunking

`chunker.py` splits speech segments into chunks suitable for STT:

- **Target duration**: 2-6 seconds per chunk
- **Overlap**: 300ms between adjacent chunks for context continuity
- **Output**: `list[AudioChunk]` with PCM data and timestamps

## Transcript Worker

`worker.py` orchestrates the full VAD → chunk → STT pipeline:

- `AudioBuffer` — per-user PCM accumulator
  - Threshold-based processing (doesn't process until enough audio buffered)
  - Resets after processing
- `transcript_loop_once(buffer, stt, detector)` — runs one processing cycle
  - Returns `list[TranscriptEvent(speaker_id, text, timestamp)]`

## Discord Integration

### VoiceIngestSink (`voice_ingest.py`)

Implements `discord-ext-voice-recv` sink interface:
1. Receives raw stereo PCM at 48kHz from Discord
2. Converts to mono 16kHz (SDK format)
3. Routes to per-user `AudioBuffer`
4. Triggers `transcript_loop_once()` when buffer threshold met
5. Emits `TranscriptEvent` via callback

### TranscriptBuffer (`voice_ingest.py`)

Rolling buffer of recent transcripts per guild:
- Max 50 events, max 5 minutes age
- Used by shitpost command for voice context
- Keyed by guild_id (one voice connection per guild)

### VoiceKeepalive (`voice_resilience.py`)

Connection health management:
- Periodic heartbeat pings
- Detects stale connections
- Automatic reconnection on unexpected disconnect
- Tracks expected vs unexpected disconnects

### VoiceActor (`voice_actor.py`)

Experimental actor-based voice management:
- Behind `USE_VOICE_ACTOR` environment variable
- Encapsulates voice state in actor pattern
- Thread-safe message passing

## CLI Transcription

The CLI `transcribe` command (`src/clanker_cli/commands/transcribe.py`) uses the same SDK pipeline:

1. Reads WAV file (mono 16-bit only)
2. Optionally runs VAD (`--vad/--no-vad`)
3. Wraps PCM in WAV container for STT provider
4. Calls `STT.transcribe()`

## Debugging

### VOICE_DEBUG mode

Enable with environment variables:
```bash
VOICE_DEBUG=1 VOICE_DEBUG_DIR=./voice_debug make run
```

Captures to `voice_debug/`:
- Raw PCM audio per user
- VAD segment boundaries
- Transcription results
- Timing information

### Audio Pipeline Script

```bash
# Download test audio
make download-test-audio

# Test VAD only (no API key needed)
python scripts/test_audio_pipeline.py

# Full STT test
OPENAI_API_KEY=sk-... python scripts/test_audio_pipeline.py --stt
```

Reports:
- VAD segment detection (Silero vs Energy comparison)
- Word Error Rate (WER) for STT accuracy
- Multi-speaker handling (AMI corpus)

### Session Analysis

```bash
python scripts/analyze_voice_session.py voice_debug/<session>/
```

## Common Gotchas

- **PCM byte math**: `bytes_per_ms = sample_rate * 2 // 1000` (16-bit = 2 bytes/sample)
- **WAV wrapping**: OpenAI STT expects WAV-formatted bytes, not raw PCM. Use `_pcm_to_wav()` in CLI transcribe or `io.BytesIO` + `wave.open("wb")`
- **Silero cold start**: First inference takes ~500ms. Use `warmup_voice_detector()` at startup
- **Discord stereo**: Discord audio is always stereo 48kHz. Conversion to mono 16kHz must happen before SDK processing
- **opus requirement**: Discord voice requires libopus. Bot loads it at startup and fails fast if missing. Docker image includes it
