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
| LLM | OpenAI | `providers/openai/llm.py` |
| LLM | Anthropic | `providers/anthropic/llm.py` |
| STT | OpenAI Whisper | `providers/openai/stt.py` |
| TTS | ElevenLabs | `providers/elevenlabs/tts.py` |
| Image | Memegen | `providers/memegen/image.py` |

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
- Silero VAD (ML-based, default) with EnergyVAD fallback
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

### Persistence (`clanker_bot/persistence/`)

SQL-based persistence using sqlc-generated queries with SQLAlchemy async:

| Component | Purpose |
|-----------|---------|
| `connection.py` | SQLAlchemy async engine management |
| `sql_feedback.py` | FeedbackStore implementation |
| `db/schema.sql` | Database schema (tables, indexes) |
| `db/queries/*.sql` | sqlc query definitions |
| `generated/` | sqlc-generated Python code (DO NOT EDIT) |

**FeedbackStore Protocol:**

```python
class FeedbackStore(Protocol):
    async def record(self, interaction: Interaction) -> None: ...
    async def get_user_stats(self, user_id: str, ...) -> dict[Outcome, int]: ...
    async def get_recent_interactions(self, user_id: str, ...) -> list[Interaction]: ...
    async def get_acceptance_rate(self, user_id: str, command: str) -> float: ...
```

**Why sqlc?**
- Type-safe query generation from raw SQL
- No ORM overhead; explicit SQL control
- Generated dataclasses match schema exactly

**Regenerating queries:**
```bash
sqlc generate
python3 scripts/fix_sqlc_placeholders.py  # Convert ? to :pN for SQLAlchemy
```

### Discord Bot Host (`clanker_bot/`)

| Module | Responsibility |
|--------|---------------|
| `main.py` | Entry point, dependency injection, health server |
| `commands.py` | Slash command registration |
| `command_handlers/` | Command implementations (chat, voice, admin, shitpost) |
| `views/` | Discord UI views (shitpost preview buttons) |
| `voice_ingest.py` | Voice receive integration with SDK pipeline |
| `discord_adapter.py` | Voice session management |
| `cogs/` | Discord cogs (VC monitoring, auto-leave) |
| `logging_config.py` | Structured logging with file rotation |
| `health.py` | Health check HTTP endpoint (`/status`) |
| `metrics.py` | Observability counters/gauges |

**Available Slash Commands:**

| Command | Handler | Description |
|---------|---------|-------------|
| `/chat` | `command_handlers/chat.py` | Chat with LLM |
| `/speak` | `command_handlers/chat.py` | Chat with TTS response |
| `/shitpost` | `command_handlers/chat.py` | Generate meme previews |
| `/join` | `command_handlers/voice.py` | Join voice channel |
| `/leave` | `command_handlers/voice.py` | Leave voice channel |
| `/transcript` | `command_handlers/transcript.py` | Show recent voice transcripts |
| `/admin_*` | `command_handlers/admin.py` | Admin commands |

**Thread Auto-Reply:** Messages in bot-created threads (`clanker-{hex}`) automatically get LLM responses via `command_handlers/thread_chat.py`.

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

### ML-Based VAD with Fallback

**Decision:** Use Silero VAD (ML-based) by default with EnergyVAD fallback.

**Rationale:**
- Silero VAD provides high-accuracy speech detection
- EnergyVAD (RMS-based) serves as lightweight fallback when torch unavailable
- Voice optional dependency (`[voice]`) keeps base install minimal
- Warmup function pre-loads model to avoid first-request latency

### Module-Level Database Engine

**Decision:** Use a module-level global `AsyncEngine` in `persistence/connection.py` with explicit `init_pool()`/`close_pool()` lifecycle.

**Rationale:**
- Standard pattern for single-process applications (Discord bot runs as one process)
- SQLAlchemy engine manages connection pooling internally; creating multiple engines wastes resources
- Lazy initialization (`_engine` starts `None`) avoids startup overhead when persistence is disabled
- The `SqlFeedbackStore` is injected via `BotDependencies`, hiding the global from the rest of the codebase
- Tests call `close_pool()` in fixtures to reset state between test files

**Scaling considerations:**
- Works well with Neon Postgres for production (asyncpg driver, connection pooling)
- Single bot instance: global engine is sufficient
- Multiple bot processes: each has its own pool (Postgres handles many connections)
- High write volume (10K+/min): would need write batching, not engine changes

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
- VAD implementations in `vad.py` (SileroVAD default, EnergyVAD fallback)
- Audio format conversions via `providers/audio_utils.py`
- Debug capture system in `voice/debug/` (enable with `VOICE_DEBUG=1`)
- Add speaker diarization in `worker.py`
- Implement real-time streaming STT
