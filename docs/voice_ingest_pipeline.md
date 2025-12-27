# Voice Ingest Pipeline

## Overview

The voice pipeline captures Discord audio, detects speech, and transcribes to text.

```
Discord voice_recv thread          Async world
        │                              │
        │  write()                     │
        └──────► buffer PCM            │
                    │                  │
                    │     _process_loop() (every 1s)
                    │          │
                    └──────────┴──► should_process() ──► STT
```

## Discord voice acquisition
- Uses `discord-ext-voice-recv` with `VoiceRecvClient` for per-user PCM frames
- **Requires libopus** for audio decoding (`apt install libopus0`)
- Opus is loaded explicitly at bot startup; fails fast if unavailable

## Opus decoding
- Expected input: 16-bit mono PCM at 48kHz (Discord native sample rate)
- Opus decoding performed by discord.py using libopus
- Bot explicitly loads opus at startup via `discord.opus._load_default()`

## VAD strategy
- **SileroVAD** (default): ML-based, high accuracy, requires torch (~500MB)
- **EnergyVAD** (fallback): RMS-based, moderate accuracy, no dependencies
- Silero model pre-downloaded in Docker to avoid runtime fetching

## Processing architecture
- `VoiceIngestSink.write()`: Called from voice_recv thread, just buffers data (no async)
- `VoiceIngestSink._process_loop()`: Async background task, checks every 1s
- When buffer exceeds threshold (~10s of audio), triggers STT processing
- Clean separation: threads buffer, async processes

## Chunking rules
- Buffer threshold: 10 seconds (configurable via `chunk_seconds`)
- Silence gap: 1000ms triggers utterance split (configurable via `max_silence_ms`)
- Chunks emitted per speaker (Discord user_id)

## Transcript buffer
- `TranscriptBuffer` maintains rolling buffer of recent transcripts per guild
- Max 50 events, max 5 minutes age
- Used by `/shitpost` for voice context and `/transcript` for debugging
