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

## Audio format handling
- Discord delivers **stereo 48kHz 16-bit PCM** (2 channels, 4 bytes/sample frame)
- SDK expects **mono 48kHz PCM** (source-agnostic)
- Whisper expects **mono 16kHz PCM**
- `AudioFormat` dataclass describes formats: `DISCORD_FORMAT`, `SDK_FORMAT`, `WHISPER_FORMAT`
- Conversion at Discord boundary: `convert_pcm(DISCORD_FORMAT, SDK_FORMAT)` in `voice_ingest.py`

## Opus decoding
- Opus decoding performed by discord.py using libopus
- Bot explicitly loads opus at startup via `discord.opus._load_default()`

## VAD strategy
- **SileroVAD** (default): ML-based, high accuracy, requires torch (~500MB)
- **EnergyVAD** (fallback): RMS-based, moderate accuracy, no dependencies
- Silero model pre-downloaded in Docker to avoid runtime fetching

## Processing architecture
- `VoiceIngestSink.write()`: Called from voice_recv thread, just buffers data (no async)
- `VoiceIngestSink._process_loop()`: Async background task, checks every 1s
- Processing triggers when:
  - Buffer exceeds threshold (~7.5s of audio), OR
  - Idle timeout reached (~3s since last audio with buffered data)
- Clean separation: threads buffer, async processes

## Chunking rules
- Buffer threshold: 7.5 seconds (configurable via `chunk_seconds`)
- Idle flush timeout: 3 seconds (configurable via `idle_timeout_seconds`)
- Silence gap: 1000ms triggers utterance split (configurable via `max_silence_ms`)
- Chunks emitted per speaker (Discord user_id)

The idle flush mechanism ensures short utterances get transcribed quickly (~3s after user stops speaking) rather than waiting for the full buffer threshold.

## Transcript buffer
- `TranscriptBuffer` maintains rolling buffer of recent transcripts per guild
- Max 50 events, max 5 minutes age
- Used by `/shitpost` for voice context and `/transcript` for debugging

## Sample rate handling
- Discord sends 48kHz audio
- Whisper is optimized for 16kHz
- Pipeline automatically resamples before STT via `audio_utils.resample_wav()`

## Debugging
See **[voice-debugging.md](voice-debugging.md)** for:
- Debug capture system (`VOICE_DEBUG=1`)
- Session analysis tools
- Common transcription issues
