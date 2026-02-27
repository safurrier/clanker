# Architecture

System design and architectural decisions for Clanker9000.

## System Overview

Clanker9000 follows an **SDK-first architecture** with clean separation between:

1. **Clanker SDK** (`src/clanker/`) — Reusable library with no Discord dependencies
2. **CLI** (`src/clanker_cli/`) — Click-based terminal interface consuming the SDK
3. **Discord Bot Host** (`src/clanker_bot/`) — Discord.py integration layer

```
┌─────────────────────────────────────────────────────────────┐
│                      Discord Bot Host                       │
│  ┌─────────────┐ ┌─────────────┐ ┌───────────────────────┐ │
│  │  Commands   │ │Voice Ingest │ │  Health/Metrics        │ │
│  └──────┬──────┘ └──────┬──────┘ └───────────────────────┘ │
│         │               │                                   │
│         └───────┬───────┘                                   │
│                 ▼                                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    Clanker SDK                          ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐││
│  │  │ respond  │ │ models   │ │ voice/*  │ │ shitposts  │││
│  │  └────┬─────┘ └──────────┘ └────┬─────┘ └────────────┘││
│  │       │                         │                      ││
│  │       └────────────┬────────────┘                      ││
│  │                    ▼                                   ││
│  │  ┌─────────────────────────────────────────────────────┐│
│  │  │                   Providers                         ││
│  │  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌───────┐                ││
│  │  │  │ LLM │ │ STT │ │ TTS │ │ Image │                ││
│  │  │  └──┬──┘ └──┬──┘ └──┬──┘ └───┬───┘                ││
│  │  └─────┼───────┼───────┼────────┼─────────────────────┘│
│  └────────┼───────┼───────┼────────┼──────────────────────┘│
└───────────┼───────┼───────┼────────┼───────────────────────┘
            ▼       ▼       ▼        ▼
      ┌─────────────────────────────────────┐
      │           External APIs             │
      │  OpenAI  ElevenLabs  Memegen  etc.  │
      └─────────────────────────────────────┘
```

The CLI (`src/clanker_cli/`) sits alongside the bot, accessing the same SDK layer directly:

```
┌──────────┐    ┌──────────────┐
│   CLI    │    │ Discord Bot  │
│ (Click)  │    │ (discord.py) │
└────┬─────┘    └──────┬───────┘
     │                 │
     └────────┬────────┘
              ▼
     ┌────────────────┐
     │  Clanker SDK   │
     │  (providers,   │
     │   voice, etc.) │
     └────────────────┘
```

## Data Flows

### Chat Request Flow

```
User Message (Discord or CLI)
    │
    ▼
Build Context (persona, history)
    │
    ▼
respond.py
    │
    ├─► Policy.validate(context)         [optional]
    ├─► LLM.generate(context, messages)
    ├─► TTS.synthesize(response)         [optional, for speak]
    ├─► Replay log (async, fire-and-forget)
    │
    ▼
Response Message + Audio (optional)
```

### Voice Transcription Flow

```
Discord Voice Channel Audio (stereo, 48kHz)
    │
    ▼
voice_ingest.py
    ├─► stereo_to_mono()
    ├─► resample 48kHz → 16kHz
    │
    ▼
AudioBuffer (per user)
    │
    ├─► should_process() threshold check
    │
    ▼
transcript_loop_once()
    ├─► detect_speech_segments() (VAD)
    ├─► chunk_segments() (chunker)
    ├─► transcribe() each chunk (STT)
    │
    ▼
TranscriptEvent(speaker_id, text)
    │
    ▼
on_transcript callback → optional chat response
```

### Shitpost Generation Flow

```
Topic + Template
    │
    ▼
sample_template() or sample_meme_template()
    │
    ▼
build_request() → ShitpostRequest
    │
    ▼
render_shitpost() or render_meme_text()
    │
    ├─► LLM.generate() with template prompt
    │
    ▼
ShitpostResult or MemeLines
    │
    ▼
Output (text, or memegen URL for memes)
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

### SDK/Host Separation

**Decision:** Keep Discord.py dependencies isolated to `clanker_bot/`.

**Rationale:**
- SDK can be tested without Discord infrastructure
- SDK can be reused in CLI tools, web APIs, etc.
- Clear boundaries prevent leaky abstractions

### Async-First Design

**Decision:** All I/O operations are async.

**Rationale:**
- Discord.py is async-native
- LLM/TTS/STT API calls benefit from concurrency
- Non-blocking voice processing

### Fire-and-Forget Replay Logging

**Decision:** Replay log writes are async and non-blocking.

**Rationale:**
- Response latency unaffected by I/O
- Log failures don't break chat flow
- Background task handles persistence
- CLI uses `run_async()` to drain these tasks before exit

### Module-Level Database Engine

**Decision:** Module-level global `AsyncEngine` with explicit `init_pool()`/`close_pool()`.

**Rationale:**
- Standard pattern for single-process Discord bot
- SQLAlchemy manages connection pooling internally
- Lazy initialization avoids overhead when persistence is disabled
- Tests call `close_pool()` in fixtures to reset state

### ML-Based VAD with Fallback

**Decision:** Silero VAD default, EnergyVAD fallback.

**Rationale:**
- Silero provides high-accuracy speech detection
- EnergyVAD serves as lightweight fallback when torch unavailable
- Voice is an optional dependency (`[voice]`) to keep base install minimal
