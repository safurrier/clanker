# Voice Module — Agent Instructions

SDK-level voice processing pipeline: VAD, audio chunking, and transcription orchestration. No Discord dependencies.

## File Structure

```
voice/
├── __init__.py
├── formats.py          # AudioFormat abstraction (DISCORD_FORMAT, SDK_FORMAT, WHISPER_FORMAT)
├── vad.py              # Voice Activity Detection (Silero/Energy)
├── chunker.py          # Audio chunking logic
├── worker.py           # Transcription worker orchestration
└── debug/
    ├── __init__.py
    ├── capture.py      # Debug audio capture system
    └── models.py       # Debug capture data models
```

## Pipeline Overview

```
Raw PCM Audio
    │
    ▼
VAD (vad.py)
    │  detect_speech_segments() → list[SpeechSegment]
    ▼
Chunking (chunker.py)
    │  chunk_segments() → list[AudioChunk]
    ▼
STT (via provider)
    │  transcribe() each chunk
    ▼
TranscriptEvent(speaker_id, text, timestamp)
```

## Audio Formats

Defined in `formats.py` as `AudioFormat` dataclass:

| Format | Sample Rate | Channels | Bit Depth | Use |
|--------|------------|----------|-----------|-----|
| `DISCORD_FORMAT` | 48000 Hz | 2 (stereo) | 16-bit | Raw Discord audio |
| `SDK_FORMAT` | 16000 Hz | 1 (mono) | 16-bit | Internal processing |
| `WHISPER_FORMAT` | 16000 Hz | 1 (mono) | 16-bit | Whisper STT input |

Conversion between formats uses `providers/audio_utils.py` (`stereo_to_mono()`, `convert_pcm()`, `resample_pcm()`).

## VAD (Voice Activity Detection)

Two implementations in `vad.py`:

### SileroVAD (default)
- ML-based, high accuracy
- Requires `torch` and `numpy` (optional `[voice]` dependency)
- Pre-loaded via `warmup_voice_detector()` to avoid first-request latency
- Processes 512-sample frames (32ms at 16kHz)

### EnergyVAD (fallback)
- RMS energy threshold, moderate accuracy
- Zero dependencies beyond stdlib
- Good enough for clear speech, struggles with background noise

### Key functions
- `resolve_detector(prefer_silero=True)` — returns best available detector
- `detect_speech_segments(pcm_bytes, sample_rate, detector)` — returns `list[SpeechSegment]`
- Each `SpeechSegment` has `start_ms` and `end_ms`

## Chunking

`chunker.py` splits speech segments into processable chunks:
- Target: 2-6 second chunks
- 300ms overlap for context continuity
- Returns `AudioChunk` objects with PCM data and timestamps

## Transcript Worker

`worker.py` coordinates the full pipeline:
- `AudioBuffer` — per-user PCM accumulator with threshold-based processing triggers
- `transcript_loop_once()` — runs one VAD → chunk → STT cycle
- Emits `TranscriptEvent` objects consumed by Discord layer

## Debug Capture

Enable with `VOICE_DEBUG=1` and `VOICE_DEBUG_DIR=./voice_debug`:
- Captures raw PCM, VAD segments, and transcription results
- Useful for diagnosing missed speech, false positives, threshold tuning
- `capture.py` handles I/O, `models.py` defines capture data structures

## Testing

- `tests/test_voice_chunker.py` — chunking logic
- `tests/test_voice_worker.py` — worker orchestration
- `tests/test_audio_formats.py` — format conversion
- `tests/test_audio_utils.py` — audio utility functions
- `tests/test_real_audio.py` — real audio samples (requires `make download-test-audio`)
- `tests/test_debug_capture.py` — debug capture system

## Gotchas

- Silero VAD requires torch which is ~500MB; the `[voice]` optional dependency group handles this
- PCM byte math: `bytes_per_ms = sample_rate * 2 // 1000` (16-bit = 2 bytes per sample)
- All audio processing assumes mono 16-bit PCM at 16kHz internally
- The Discord layer (`clanker_bot/voice_ingest.py`) handles stereo-to-mono conversion before feeding this pipeline
