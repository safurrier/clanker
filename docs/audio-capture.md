# Audio Capture and Transcription Pipeline

The Clanker9000 bot includes a speaker-aware voice transcription system that captures Discord voice chat, detects speech using ML-based VAD, and transcribes utterances to text with temporal ordering across multiple speakers.

## Overview

The audio pipeline consists of four main components:

1. **Voice Activity Detection (VAD)** - Identifies speech segments in audio using Silero VAD (ML) or EnergyVAD (RMS) fallback
2. **Utterance Grouping** - Merges speech segments into natural utterances based on silence gaps
3. **Transcription** - Converts audio chunks to text using OpenAI Whisper
4. **Event Ordering** - Sorts transcript events chronologically across speakers

## Architecture

```
Discord Voice Channel
  ↓ (per-user PCM streams)
VoiceRecvClient (discord-ext-voice-recv)
  ↓
VoiceIngestWorker (buffers PCM per speaker)
  ↓
SpeechDetector.detect() → [SpeechSegment, ...]
  ↓
build_utterances() → [Utterance, ...] (grouped by silence)
  ↓
STT.transcribe() → "transcript text" (per utterance)
  ↓
TranscriptEvent (speaker_id, text, start_time, end_time)
  ↓
Sorted by timestamp → Chronological conversation
```

## Voice Activity Detection (VAD)

### Two Implementations

| Implementation | Accuracy | Dependencies | Use Case |
|----------------|----------|--------------|----------|
| **SileroVAD** | High (~95%) | torch, numpy (~500MB) | Production (default) |
| **EnergyVAD** | Moderate (~70%) | Built-in (audioop) | Fallback / minimal env |

### SileroVAD (Default)

ML-based speech detection using the Silero VAD model:

```python
from clanker.voice.vad import SileroVAD

detector = SileroVAD(warmup=True)  # Pre-loads model
segments = detector.detect(pcm_bytes, sample_rate_hz=48000)
# Returns: [SpeechSegment(start_ms=0, end_ms=1200), ...]
```

**How it works:**
1. Converts PCM to float32 normalized samples
2. Resamples to 16kHz (Silero requirement)
3. Processes 512-sample windows (~32ms at 16kHz)
4. Uses Silero model to compute speech probability (0.0-1.0)
5. Segments are speech when prob >= 0.4

**Installation:**
```bash
uv pip install -e ".[voice]"
```

**Warmup on startup** (recommended):
```python
from clanker_bot.voice_ingest import warmup_voice_detector

# On bot ready
detector = await warmup_voice_detector(prefer_silero=True)
# Logs: "Silero VAD ready" or "Using EnergyVAD fallback"
```

### EnergyVAD (Fallback)

RMS threshold-based detection (simple, no dependencies):

```python
from clanker.voice.vad import EnergyVAD

detector = EnergyVAD(
    frame_ms=30,        # Frame size
    threshold=500,      # RMS threshold
    padding_ms=300,     # Silence padding
)
segments = detector.detect(pcm_bytes, sample_rate_hz=48000)
```

**How it works:**
1. Splits audio into 30ms frames
2. Computes RMS (root mean square) energy per frame
3. Marks frames as speech if RMS >= threshold
4. Pads silence (300ms) to avoid cutting off speech

**Tradeoffs:**
- ✅ No dependencies, lightweight
- ✅ Fast processing
- ❌ Less accurate (noise triggers false positives)
- ❌ Struggles with quiet speakers

## Utterance Grouping

Speech segments are merged into natural utterances based on silence gaps:

```python
from clanker.voice.worker import _build_utterances

segments = [
    SpeechSegment(start_ms=0, end_ms=400),
    SpeechSegment(start_ms=600, end_ms=1000),  # 200ms gap
    SpeechSegment(start_ms=1800, end_ms=2200), # 800ms gap
]
utterances = _build_utterances(segments, max_silence_ms=500)
# Returns: [
#   Utterance(start_ms=0, end_ms=1000),     # Merged (gap < 500ms)
#   Utterance(start_ms=1800, end_ms=2200),  # Separate (gap > 500ms)
# ]
```

**Benefits:**
- Natural speech chunks (not individual words)
- Reduces transcription API calls
- Better context for Whisper STT
- Preserves speaker pauses

**Configuration:**
- `max_silence_ms`: Maximum gap to merge (default: 500ms)
- Shorter values → more utterances (fragmented)
- Longer values → fewer utterances (merged pauses)

## Transcription Flow

### Per-Speaker Buffering

Audio is buffered separately for each Discord user:

```python
from clanker_bot.voice_ingest import VoiceIngestWorker

worker = VoiceIngestWorker(
    stt=openai_whisper,
    sample_rate_hz=48000,       # Discord voice rate
    chunk_seconds=2.0,          # Process every 2 seconds
    max_silence_ms=500,         # Utterance grouping
    detector=silero_vad,        # VAD implementation
)

# As audio arrives (from Discord)
worker.add_pcm(user_id=123, pcm_bytes=chunk, recorded_at=datetime.now())

# When buffer threshold is reached
if worker.should_process():
    events = await worker.process_once()
```

### Processing Pipeline

1. **Buffer accumulation**: Collect 2 seconds of audio per speaker
2. **VAD detection**: Find speech segments in each buffer
3. **Utterance grouping**: Merge segments within 500ms
4. **WAV encoding**: Wrap PCM in WAV container for Whisper
5. **Transcription**: Send each utterance to STT
6. **Event creation**: Build `TranscriptEvent` with timestamps
7. **Chronological sorting**: Order events by `start_time`

### TranscriptEvent Schema

Each transcribed utterance produces:

```python
@dataclass(frozen=True)
class TranscriptEvent:
    speaker_id: int         # Discord user_id
    chunk_id: str          # "{speaker_id}-{index}"
    text: str              # Transcribed text
    chunk: AudioChunk      # Audio boundaries (ms)
    start_time: datetime   # Absolute timestamp
    end_time: datetime     # Absolute timestamp
```

### Multi-Speaker Ordering

Events are sorted chronologically across all speakers:

```python
# Example: 2 speakers talking
events = [
    TranscriptEvent(speaker_id=1, text="Hello", start_time=12:00:00.0),
    TranscriptEvent(speaker_id=2, text="Hi there", start_time=12:00:00.5),
    TranscriptEvent(speaker_id=1, text="How are you?", start_time=12:00:01.2),
]
```

**Use cases:**
- Conversation transcripts
- Speaker attribution
- Meeting notes
- Context for LLM prompts

## Configuration

### Buffer Size (`chunk_seconds`)

Controls **when** to process accumulated audio buffers.

| Value | Latency | API Calls | Use Case |
|-------|---------|-----------|----------|
| **10s** (default) | ~10s | Moderate | Conversations, voice chat |
| **30s** | ~30s | Few | Meetings, monologues |
| **60s** | ~60s | Minimal | Long-form (podcasts, lectures) |
| **2s** | ~2s | Many | Real-time (NOT recommended) |

**Trade-off:**
- **Smaller** = Lower latency, more API calls, may cut off speakers
- **Larger** = Higher latency, fewer API calls, captures complete thoughts

**Example:**
```python
# For voice chat (recommended)
worker = VoiceIngestWorker(stt=stt, chunk_seconds=10.0)

# For meeting transcription
worker = VoiceIngestWorker(stt=stt, chunk_seconds=30.0)

# For podcasts/lectures
worker = VoiceIngestWorker(stt=stt, chunk_seconds=60.0)
```

**Memory impact:**
- 10s buffer = ~960 KB per speaker
- 30s buffer = ~2.9 MB per speaker
- 10 speakers × 30s = ~29 MB total (acceptable)

### Silence Gap (`max_silence_ms`)

Controls **how** to split utterances within a buffer.

| Value | Behavior | Use Case |
|-------|----------|----------|
| **1000ms** (default) | 1 second silence = new utterance | Natural speech pauses |
| **500ms** | 0.5 second silence = new utterance | Faster speakers |
| **1500ms** | 1.5 second silence = new utterance | Thoughtful/slow speakers |

**Trade-off:**
- **Smaller** = More utterances, fragmented speech
- **Larger** = Fewer utterances, merged pauses

**Example:**
```python
# Fast speakers (split on short pauses)
worker = VoiceIngestWorker(stt=stt, max_silence_ms=500)

# Normal speech (recommended)
worker = VoiceIngestWorker(stt=stt, max_silence_ms=1000)

# Slow/thoughtful speakers (allow longer pauses)
worker = VoiceIngestWorker(stt=stt, max_silence_ms=1500)
```

**Important:** Even with large `chunk_seconds`, utterances still split naturally by silence!

---

## Integration

### Bot Startup

```python
from clanker_bot.voice_ingest import warmup_voice_detector, start_voice_ingest

@bot.event
async def on_ready():
    # Pre-load Silero VAD model
    global voice_detector
    voice_detector = await warmup_voice_detector(prefer_silero=True)
```

### Joining Voice Channel

```python
from clanker_bot.voice_ingest import start_voice_ingest, voice_client_cls

# Join channel
voice_client = await voice_channel.connect(cls=voice_client_cls())

# Start transcription
async def on_transcript(event: TranscriptEvent):
    print(f"[{event.speaker_id}] {event.text}")

await start_voice_ingest(
    voice_client=voice_client,
    stt=openai_stt,
    on_transcript=on_transcript,
    detector=voice_detector,
    max_silence_ms=500,
)
```

### Building LLM Context

```python
from clanker.voice.worker import build_context_from_event

# Convert transcript event to bot context
context = build_context_from_event(base_context, event)
# context.messages = [Message(role="user", content=event.text)]
# context.metadata = {"speaker_id": "123", "audio_chunk_id": "123-0"}
```

## Performance

### Latency

| Stage | Typical Latency |
|-------|----------------|
| VAD detection | ~50ms (Silero) / ~10ms (Energy) |
| Utterance grouping | ~1ms |
| WAV encoding | ~5ms |
| Whisper transcription | 500-2000ms (depends on chunk length) |
| **Total** | ~600-2100ms |

### Resource Usage

| Component | CPU | Memory | Disk |
|-----------|-----|--------|------|
| SileroVAD | Medium | ~500MB | ~30MB (model) |
| EnergyVAD | Low | ~1MB | 0MB |
| Whisper API | N/A (remote) | Minimal | 0MB |

### Optimization Tips

1. **Use warmup**: Pre-load Silero model on startup
2. **Tune chunk_seconds**: Longer = fewer API calls but higher latency
3. **Adjust max_silence_ms**: Shorter = more utterances but better responsiveness
4. **Monitor buffers**: Large buffers may indicate slow STT

## Testing

### Unit Tests

```bash
# All voice tests
uv run pytest tests/test_voice*.py -v

# Specific test
uv run pytest tests/test_voice_worker.py::test_transcript_loop_once -v
```

### Test Fixtures

Audio fixtures in `tests/audio_fixtures/`:
- `test_tone.wav` - Simple test tone
- Add more fixtures for different scenarios

### Example: Testing VAD

```python
from clanker.voice.vad import SileroVAD, EnergyVAD
import wave

# Load test audio
with wave.open("tests/audio_fixtures/test_tone.wav", "rb") as wf:
    pcm_bytes = wf.readframes(wf.getnframes())
    sample_rate = wf.getframerate()

# Test Silero VAD
detector = SileroVAD(warmup=True)
segments = detector.detect(pcm_bytes, sample_rate)
assert len(segments) > 0
```

## Troubleshooting

### "Silero VAD unavailable, falling back to EnergyVAD"

**Cause**: torch/numpy not installed

**Fix**:
```bash
uv pip install -e ".[voice]"
```

### Poor transcription quality

**Possible causes:**
1. **Noisy environment**: VAD includes background noise
   - Solution: Increase `EnergyVAD.threshold` or use Silero
2. **Clipped speech**: Utterances split mid-word
   - Solution: Increase `max_silence_ms` (try 700-1000ms)
3. **Too long chunks**: Exceeds Whisper limits
   - Solution: Decrease `chunk_seconds` (try 1.5-2.0s)

### High latency

**Possible causes:**
1. **Slow STT API**: Network or Whisper processing time
   - Solution: Use smaller audio chunks, check network
2. **Large buffers**: Too much audio accumulating
   - Solution: Decrease `chunk_seconds`
3. **Silero VAD on CPU**: Model inference slow
   - Solution: Use GPU or switch to EnergyVAD

### Overlapping speakers

**Current limitation**: Each speaker processed independently, overlaps may cause:
- Simultaneous events (both speakers at same timestamp)
- Cross-talk in transcripts (if audio mixed)

**Workarounds:**
- Sort by `start_time` (already done)
- Merge close events (< 100ms apart)
- Use speaker_id to attribute text

## Future Improvements

Potential enhancements (see `VOICE_IMPROVEMENTS.md` for details):

1. **Replace audioop with numpy** - Python 3.13 compatibility
2. **Configurable VAD parameters** - Via config.yaml
3. **E2E audio scenario tests** - Long monologues, overlapping speakers, silence
4. **Better error handling** - Timeouts, malformed audio
5. **Metrics/monitoring** - VAD accuracy, transcription latency
6. **Diarization support** - Automatic speaker identification
7. **Real-time streaming** - Incremental transcription

## Best Practices

1. **Always warmup Silero VAD on startup** - Avoids first-request latency
2. **Use Silero in production** - Better accuracy than Energy
3. **Tune `max_silence_ms` for your use case** - Conversational (500ms) vs monologue (1000ms)
4. **Monitor transcription latency** - Slow API calls block processing
5. **Test with real Discord audio** - Test fixtures may not match production
6. **Handle transcript events asynchronously** - Don't block voice pipeline
7. **Store events with timestamps** - Enables playback and analysis

## Dependencies

**Required:**
- `discord.py>=2.4.0`
- `discord-ext-voice-recv>=0.4.0`

**Optional (voice support):**
- `torch>=2.0.1`
- `numpy>=1.25.0`

**Install:**
```bash
# Minimal (EnergyVAD only)
uv pip install -e .

# With voice support (Silero VAD)
uv pip install -e ".[voice]"
```

## See Also

- [ARCHITECTURE.md](./ARCHITECTURE.md) - Overall system design
- [voice_ingest_pipeline.md](./voice_ingest_pipeline.md) - Original v1 design notes
- [DOCKER_DEPLOYMENT.md](../docker/DEPLOYMENT.md) - Docker setup with pre-downloaded Silero model
- `src/clanker/voice/` - Implementation source code
- `tests/test_voice_*.py` - Test suite
