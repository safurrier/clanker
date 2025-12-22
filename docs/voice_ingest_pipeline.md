# Voice Ingest Pipeline (v1)

## Discord voice acquisition
- Use `discord-ext-voice-recv` with a `VoiceRecvClient` to tap per-user PCM frames.
- Keep acquisition isolated in the Discord host layer and feed PCM bytes into the SDK pipeline.

## Opus decoding
- Expected input is 16-bit mono PCM at 48kHz (Discord native voice sample rate).
- Opus decoding should be performed by the host layer (libopus + ffmpeg).

## VAD strategy
- V1 uses simple energy-based VAD to keep dependencies light.
- Frame size: 30ms, padding: 300ms, threshold tuned for typical Discord audio.
- Silero VAD remains the preferred upgrade path once torch deps are acceptable.

## Chunking rules
- Target chunk sizes: 2–6s.
- 300ms overlap between chunks to preserve context.
- Chunks emitted per speaker (Discord user_id).

## Transcript merge
- Each chunk emits a transcript event with metadata:
  - `speaker_id` (Discord user_id)
  - `audio_chunk_id`
- Merge into a single timeline by `(timestamp, speaker_id)` ordering.
