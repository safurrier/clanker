# Architecture

System design and architectural decisions for Clanker9000.

## System Overview

Clanker9000 follows a **SDK-first architecture** with clean separation between:

1. **Clanker SDK** (`src/clanker/`) - Reusable library with no Discord dependencies
2. **Discord Bot Host** (`src/clanker_bot/`) - Discord.py integration layer

This design enables:
- Unit testing without Discord infrastructure
- Reuse of SDK components in other contexts (CLI, web API, etc.)
- Clear boundaries between business logic and platform integration

```
┌─────────────────────────────────────────────────────────────┐
│                      Discord Bot Host                        │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │  Commands   │ │Voice Ingest │ │   Health/Metrics        ││
│  └──────┬──────┘ └──────┬──────┘ └─────────────────────────┘│
│         │               │                                    │
│         └───────┬───────┘                                    │
│                 ▼                                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    Clanker SDK                          ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ ││
│  │  │ respond  │ │ models   │ │ voice/*  │ │ shitposts  │ ││
│  │  └────┬─────┘ └──────────┘ └────┬─────┘ └────────────┘ ││
│  │       │                         │                       ││
│  │       └────────────┬────────────┘                       ││
│  │                    ▼                                    ││
│  │  ┌─────────────────────────────────────────────────────┐││
│  │  │                   Providers                         │││
│  │  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌───────┐ ┌────────┐     │││
│  │  │  │ LLM │ │ STT │ │ TTS │ │ Image │ │ Policy │     │││
│  │  │  └──┬──┘ └──┬──┘ └──┬──┘ └───┬───┘ └────────┘     │││
│  │  └─────┼───────┼───────┼────────┼─────────────────────┘││
│  └────────┼───────┼───────┼────────┼──────────────────────┘│
└───────────┼───────┼───────┼────────┼───────────────────────┘
            ▼       ▼       ▼        ▼
      ┌─────────────────────────────────────┐
      │           External APIs             │
      │  OpenAI  ElevenLabs  Memegen  etc.  │
      └─────────────────────────────────────┘
```

## Components

### Domain Models (`clanker/models.py`)

Core data structures used throughout the system:

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Message` | Chat message | `role`, `content` |
| `Persona` | Bot personality | `id`, `display_name`, `system_prompt`, `tts_voice` |
| `Context` | Request context | `request_id`, `persona`, `history`, `metadata` |
| `ReplayEntry` | Audit log entry | `context`, `response`, `timestamp` |

All models are **immutable** (`@dataclass(frozen=True)`) for thread safety and predictability.

### Response Orchestration (`clanker/respond.py`)

Central function that coordinates the response flow:

```python
async def respond(
    context: Context,
    llm: LLM,
    tts: TTS | None = None,
    policy: Policy | None = None,
    replay_log_path: Path | None = None,
) -> tuple[Message, bytes | None]:
```

Flow:
1. **Policy validation** - Check context against policy (if provided)
2. **LLM generation** - Call LLM provider with persona and history
3. **TTS synthesis** - Convert response to audio (if TTS provided)
4. **Replay logging** - Persist interaction to JSONL (fire-and-forget)
5. **Return** - Response message and optional audio bytes

### Provider Architecture (`clanker/providers/`)

Providers are **protocol-based** for loose coupling:

```python
# Protocol definition (providers/llm.py)
class LLM(Protocol):
    async def generate(
        self,
        context: Context,
        messages: list[Message],
        params: dict | None = None,
    ) -> Message: ...
```

**Available Providers:**

| Type | Provider | Implementation |
|------|----------|----------------|
| LLM | OpenAI | `openai_llm.py` |
| STT | OpenAI Whisper | `openai_stt.py` |
| TTS | ElevenLabs | `elevenlabs_tts.py` |
| Image | Memegen | `memegen.py` |
| Policy | Profanity Filter | `policies/profanity.py` |

**Factory Pattern:**

```python
# providers/factory.py
llm = create_llm("openai")  # Returns OpenAILLM instance
stt = create_stt("openai")  # Returns OpenAISTT instance
```

### Voice Pipeline (`clanker/voice/`)

Three-stage audio processing:

```
Audio Input → VAD → Chunking → STT → Text Output
```

**1. Voice Activity Detection** (`vad.py`)
- Energy-based detection using `audioop.rms`
- Configurable thresholds and padding
- Returns `SpeechSegment` objects with timestamps

**2. Audio Chunking** (`chunker.py`)
- Splits segments into 2-6 second chunks
- 300ms overlap for context continuity
- Returns `AudioChunk` objects

**3. Transcript Worker** (`worker.py`)
- Processes per-user audio buffers
- Coordinates VAD → Chunking → STT pipeline
- Emits `TranscriptEvent` objects

### Shitposts (`clanker/shitposts/`)

Template-based LLM content generation:

```yaml
# templates.yaml
- name: hot-take
  category: humor
  prompt: "Generate a controversial but harmless hot take about {topic}"
  tags: ["humor", "opinion"]
```

API:
- `load_templates()` - Load from YAML
- `sample_template(category)` - Random selection
- Template rendering with variable substitution

### Configuration (`clanker/config/`)

YAML-based configuration with validation:

```python
# loader.py
config = load_config("config.yaml")
# Returns ClankerConfig with validated providers and personas
```

Schema enforces:
- Required provider selections (llm, stt)
- At least one persona defined
- Default persona must exist

### Discord Bot Host (`clanker_bot/`)

| Module | Responsibility |
|--------|---------------|
| `main.py` | Entry point, dependency injection, health server |
| `commands.py` | Slash command registration (`/chat`, `/status`) |
| `voice_ingest.py` | Voice receive integration with SDK pipeline |
| `discord_adapter.py` | Voice session management |
| `admin.py` | Admin-only commands |
| `health.py` | Health check endpoint |
| `metrics.py` | Observability counters/gauges |

## Data Flow

### Chat Request Flow

```
User Message
    │
    ▼
Discord Event
    │
    ▼
commands.py (slash command handler)
    │
    ├─► Build Context (persona, history)
    │
    ▼
respond.py
    │
    ├─► Policy.validate(context)
    │
    ├─► LLM.generate(context, messages)
    │
    ├─► TTS.synthesize(response) [optional]
    │
    ├─► Replay log (async)
    │
    ▼
Response Message + Audio
    │
    ▼
Discord Reply
```

### Voice Transcription Flow

```
Voice Channel Audio
    │
    ▼
voice_recv (discord extension)
    │
    ▼
VoiceIngestSink.write(user, pcm_data)
    │
    ├─► VoiceIngestWorker.add_pcm(user_id, bytes)
    │
    ├─► should_process() check (buffer threshold)
    │
    ▼
VoiceIngestWorker.process_once()
    │
    ├─► VAD: detect_speech_segments()
    │
    ├─► Chunker: chunk_segments()
    │
    ├─► STT: transcribe() each chunk
    │
    ▼
TranscriptEvent(speaker_id, text)
    │
    ▼
on_transcript callback
    │
    ▼
Chat Flow (optional response)
```

## Design Decisions

### Protocol-Based Dependency Injection

**Decision:** Use Python `Protocol` classes instead of abstract base classes.

**Rationale:**
- Structural subtyping (duck typing with type safety)
- No inheritance required for implementations
- Easier testing with ad-hoc test doubles
- Better IDE support for protocol conformance

### Immutable Domain Models

**Decision:** All domain models use `@dataclass(frozen=True)`.

**Rationale:**
- Thread-safe by design
- Predictable behavior (no mutation surprises)
- Easy serialization/deserialization
- Enables caching and memoization

### SDK/Host Separation

**Decision:** Keep Discord.py dependencies isolated to `clanker_bot/`.

**Rationale:**
- SDK can be tested without Discord infrastructure
- SDK can be reused in CLI tools, web APIs, etc.
- Clear boundaries prevent leaky abstractions
- Easier to maintain and reason about

### Async-First Design

**Decision:** All I/O operations are async.

**Rationale:**
- Discord.py is async-native
- LLM/TTS/STT API calls benefit from concurrency
- Non-blocking voice processing
- Scales better under load

### Fire-and-Forget Replay Logging

**Decision:** Replay log writes are async and non-blocking.

**Rationale:**
- Response latency unaffected by I/O
- Log failures don't break chat flow
- Background task handles persistence
- Task reference tracked to prevent garbage collection

### Energy-Based VAD (Not ML)

**Decision:** Use simple RMS energy threshold for voice detection.

**Rationale:**
- No heavy ML dependencies (torch, etc.)
- Fast and predictable latency
- Good enough for Discord voice quality
- Silero VAD documented as upgrade path if needed

## Technical Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| Discord Framework | discord.py 2.4+ |
| Voice Receive | discord-ext-voice-recv |
| HTTP Client | httpx (async) |
| Config Parsing | PyYAML |
| Type Checking | ty |
| Linting/Formatting | ruff |
| Testing | pytest, pytest-asyncio, dpytest |
| Package Manager | uv |

## Extension Points

### Adding a New LLM Provider

1. Create `providers/anthropic_llm.py`:
   ```python
   @dataclass(frozen=True)
   class AnthropicLLM(LLM):
       api_key: str
       model: str = "claude-3-opus"

       async def generate(self, context, messages, params=None):
           # Implementation
   ```

2. Register in `providers/factory.py`:
   ```python
   _llm_registry["anthropic"] = AnthropicLLM
   ```

3. Add tests in `tests/test_anthropic_adapter.py`

### Adding a New Policy

1. Create `policies/rate_limit.py`:
   ```python
   @dataclass
   class RateLimitPolicy(Policy):
       max_requests_per_minute: int = 10

       def validate(self, context: Context) -> None:
           # Check rate limit, raise if exceeded
   ```

2. Wire into `respond()` or command handlers

### Adding Voice Features

The voice pipeline is modular:
- Replace VAD with ML-based (Silero) by implementing `detect_speech_segments`
- Add speaker diarization in `worker.py`
- Implement real-time streaming STT
