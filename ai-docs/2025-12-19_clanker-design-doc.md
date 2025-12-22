Clanker — DESIGN_DOC

Single-page design + expanded SPEC + IMPLEMENTATION notes for the Clanker9000 bot (SDK-first Discord bot with optional voice ingest, TTS, STT, and shitpost/meme features). This document is intended to be authoritative for v1 and to make future scaling decisions low-friction.

⸻

Summary (one paragraph)

Clanker is an SDK-first Discord bot: a small, testable Python library (the SDK) implementing domain logic (Context, Persona, prompts, shitpost generators) and a thin host that wires SDK calls to Discord. Voice ingestion is supported but limited: one active voice session per bot instance. Providers (LLM, STT, TTS, Image) are pluggable adapters; v1 supports a single configured provider per capability and surfaces errors instead of trying fallbacks. Testing relies on fakes/doubles and dpytest; Playwright is allowed only for local developer smoke tests (not CI). Context is immutable, serializable, and persisted for replay.

⸻

Goals
	•	Ship a minimal, delightful Discord bot for chat, shitposting, and TTS.\
	•	Keep core logic pure, testable, and independent of Discord or provider networks.\
	•	Keep runtime simple: one active VC per bot instance; explicit BUSY state.\
	•	Make future scale (multiple bot instances, worker dispatch) straightforward via Context serialization and clear adapter boundaries.

⸻

Core Principles
	•	Context as data: Every request is an immutable dataclass Context (serializable). Persist for replay/debug.
	•	Domain structs + protocols: Use dataclasses for domain models and typing.Protocol for capability contracts (LLM, STT, TTS, Image, Policy). No implicit global state.
	•	SDK / Bot separation: SDK implements business logic; Bot is thin glue handling Discord I/O and UX.
	•	Edge-only side effects: All network I/O and native libs live in adapters.
	•	Keep v1 minimal: No fallback provider logic, no cost/latency routing, minimal safety (simple profanity filter). Defer complex infra.

⸻

Minimal surface (v1)
	•	/chat -> thread-based conversation, persona injection
	•	/speak -> TTS, returns audio file
	•	/shitpost -> generate one-liners/memes/haiku/plays using existing Sparky prompts
	•	Voice join to a VC -> single session only; emits Context transcript events
	•	Persona YAMLs, provider config, and simple admin commands
	•	Tests: fakes + dpytest + audio fixture tests

⸻

SPEC.md

This SPEC is a concise, actionable reference for implementers. It includes: data models, protocols, command contract, behavior for voice, provider rules, and testing matrix.

Data models (core types)

All types are dataclasses (Python 3.10+). Keep frozen=True on Context to ensure immutability.

# models.py
from dataclasses import dataclass
from typing import List, Mapping, Optional

@dataclass(frozen=True)
class Message:
    role: str  # 'user' | 'assistant' | 'system'
    content: str

@dataclass(frozen=True)
class Persona:
    id: str
    display_name: str
    system_prompt: str
    tts_voice: Optional[str] = None
    providers: Mapping[str, str] = None  # simple provider hint map (e.g. {'llm': 'openai'})

@dataclass(frozen=True)
class Context:
    request_id: str
    user_id: int
    guild_id: Optional[int]
    channel_id: int
    persona: Persona
    messages: List[Message]
    metadata: Mapping[str, str]

Persistence: store JSON-serialized contexts in a replay log. Include timestamp and processing result. The schema must be versioned.

Protocols / Interfaces

Specify minimal required methods for each capability.

from typing import Protocol
from models import Context, Message

class LLM(Protocol):
    async def generate(self, context: Context, messages: list[Message], params: dict | None = None) -> Message: ...

class TTS(Protocol):
    async def synthesize(self, text: str, voice: str | None, params: dict | None = None) -> bytes: ...

class STT(Protocol):
    async def transcribe(self, audio_bytes: bytes, params: dict | None = None) -> str: ...

class ImageGen(Protocol):
    async def generate(self, spec: dict) -> bytes | str: ...

class Policy(Protocol):
    def validate(self, context: Context) -> None: ...

Notes: v1 adapters raise on failure — no fallback chain.

Commands (contract)
	•	/chat prompt:str -> creates a thread, constructs Context, calls respond (LLM), posts reply in thread.
	•	/speak prompt:str -> same as /chat but also calls TTS and attaches audio file.
	•	/shitpost [style] -> uses sdk/shitposts generator, which calls LLM to fill templates, may call ImageGen for memes.
	•	/join -> bot joins caller’s voice channel if not busy; returns OK or BUSY.
	•	/leave -> bot leaves voice channel, triggers meeting-end hook.

Voice ingestion behavior
	•	VoiceIngest.start(context) -> OK|BUSY where BUSY indicates an active session.
	•	Worker receives per-user buffers (Opus or PCM); code should process per-user audio, VAD, chunking, then emit Context events with metadata={'audio_chunk_id': id, 'speaker_id': uid} and messages=[Message(role='user', content='...transcript...')].
	•	Chunks: default 2–6s with 200–500ms overlap.

Provider config (v1 — explicit, minimal)

v1 intentionally supports one provider per capability. Errors propagate; no fallback chains.

Initial supported providers:
	•	LLM: OpenAI (Chat Completions)
	•	STT: Whisper (API or local)
	•	TTS: ElevenLabs

Configuration example:

llm: openai
tts: elevenlabs
stt: whisper
image: memegen

Providers are resolved via ProviderFactory and injected into respond(...).
yaml
llm: openai
tts: elevenlabs
stt: whisper
image: memegen

## Error model
- Adapter errors propagate as user-friendly errors in bot responses. Classify transient vs permanent in logs for ops.
- For voice start: return BUSY if active; otherwise attempt to join and on failure surface friendly message.

## Logging & Observability
- Log each Context (sanitized) at INFO with request_id and persona id.
- Metrics: counters for requests, errors by capability, active_voice_sessions.
- Minimal health endpoint `/status` returning JSON {uptime, active_voice, version}.

---

# IMPLEMENTATION.md

Implementation guidance: folder layout, coding guidelines, testing approach, CI notes, and templates for common operations. Follow the Python Core preferences you provided.

## Repo layout (recommended — explicit LIB / APP split)

clanker9000/                     # repo root
├─ pyproject.toml
├─ README.md                     # user-facing overview (RMD-first)
├─ src/
│  ├─ clanker/                   # LIBRARY / SDK (pure logic, no Discord imports)
│  │  ├─ init.py
│  │  ├─ models.py               # dataclasses: Context, Message, Persona
│  │  ├─ constants.py
│  │  ├─ respond.py              # core use-case: respond(context, llm, policy, tts)
│  │  ├─ providers/              # protocols + concrete provider adapters
│  │  │  ├─ init.py
│  │  │  ├─ llm.py               # LLM protocol
│  │  │  ├─ stt.py               # STT protocol
│  │  │  ├─ tts.py               # TTS protocol
│  │  │  ├─ factory.py           # ProviderFactory (v1: single provider per capability)
│  │  │  ├─ openai_llm.py        # OpenAI LLM adapter (v1 default)
│  │  │  ├─ whisper_stt.py       # Whisper STT adapter (v1 default)
│  │  │  └─ elevenlabs_tts.py    # ElevenLabs TTS adapter (v1 default)
│  │  ├─ shitposts/              # shitpost + meme generation (ported from Sparky)
│  │  │  ├─ models.py
│  │  │  ├─ templates.yaml
│  │  │  └─ api.py
│  │  └─ voice/                  # voice ingest logic (algorithmic, testable)
│  │     ├─ vad.py
│  │     ├─ chunker.py
│  │     └─ worker.py            # transcript_loop_once() exposed for tests
│  │
│  └─ clanker_bot/               # APPLICATION / HOST (Discord-specific glue)
│     ├─ init.py
│     ├─ main.py                 # entrypoint (uv run clanker_bot/main.py)
│     ├─ commands.py             # slash commands -> build Context -> call SDK
│     ├─ discord_adapter.py      # discord.py wrappers, VC join/leave
│     └─ health.py               # /status, metrics endpoints
│
└─ tests/
├─ fakes.py                   # FakeLLM, FakeSTT, FakeTTS, FakeVoiceClient
├─ test_respond.py
├─ test_shitposts.py
└─ audio_fixtures/

polymorph/
├─ README.md
├─ pyproject.toml
├─ scripts/
├─ src/polymorph/
│  ├─ __init__.py
│  ├─ main.py                # run entry (uv run main.py)
│  ├─ kernel.py              # optional later kernel wrapper
│  ├─ models.py              # dataclasses (Context, Message, Persona)
│  ├─ constants.py
│  ├─ sdk/
│  │  ├─ __init__.py
│  │  ├─ respond.py         # core use-case: respond(context, llm, policy, tts)
│  │  ├─ shitposts/
│  │  │  ├─ models.py
│  │  │  ├─ templates.yaml
│  │  │  └─ api.py
│  │  ├─ providers/
│  │  │  ├─ factory.py
│  │  │  └─ openai_adapter.py
│  ├─ adapters/
│  │  ├─ discord_adapter.py
│  │  ├─ tts_adapter.py
│  │  └─ stt_adapter.py
│  └─ workers/
│     └─ voice_worker.py
└─ tests/
   ├─ fakes.py
   ├─ test_respond.py
   ├─ test_shitposts.py
   └─ audio_fixtures/

Implementation notes & coding standards (follow the Python Core guidance)
	•	Type hints everywhere. No Dict[str, Any]. Use specific Mapping[str,str] or typed dataclasses.
	•	Dataclasses for domain models and frozen=True for Context.
	•	Imports at top of file; no inline imports except with a comment and unavoidable reason.
	•	Constants in constants.py or small module-level constants; avoid magic strings.
	•	No boolean flags on functions; prefer enums.
	•	Small focused functions; extract validation, processing, finalization helpers.
	•	Docstrings for public functions; include type expectations.

Provider factory (minimal)
	•	Implement ProviderFactory.register(name, cls) and ProviderFactory.get(name) that returns adapter instance configured from secrets.
	•	Keep adapter constructors simple and stateless; pass credentials explicitly.

respond(context, llm, policy, tts) pattern
	•	Validate: policy.validate(context)
	•	Call LLM: reply = await llm.generate(context, context.messages)
	•	If persona.tts_voice and tts configured: audio = await tts.synthesize(reply.content, persona.tts_voice)
	•	Persist context + reply + audio metadata to replay log (async background write)
	•	Return (reply, audio)

Example pseudo-code (follow style rules)

# respond.py
async def respond(context: Context, llm: LLM, policy: Policy | None, tts: TTS | None):
    if policy is not None:
        policy.validate(context)

    # generate
    reply = await llm.generate(context, context.messages)

    audio = None
    if tts is not None and context.persona.tts_voice:
        audio = await tts.synthesize(reply.content, context.persona.tts_voice)

    # async log (fire-and-forget)
    asyncio.create_task(_persist_context_result(context, reply, bool(audio)))

    return reply, audio

Voice worker implementation sketch
	•	VoiceWorker receives start(meeting_id, channel_id, voice_client) calls
	•	It runs a transcript_loop_once() method that processes per-user buffers so it can be unit-tested
	•	Use FakeVoiceClient in tests to emulate per-user buffers

Key properties
	•	Keep the worker loop testable by exposing a single-iteration method
	•	Keep Opus decoding isolated behind a function so tests can feed PCM or Opus fixtures

Shitpost module port plan (from Sparky)
	•	Copy shitposts dataclasses and template YAMLs into sdk/shitposts
	•	Implement sample_shitpost(category=None, name=None) -> ShitPost and render_shitpost(context, shitpost) which calls LLM
	•	Image generation: implement memegen adapter (optional)

Testing details (practical)
	•	tests/fakes.py contains:
	•	FakeLLM (deterministic text responses)
	•	FakeTTS (returns constant bytes)
	•	FakeSTT (returns a deterministic transcript)
	•	FakeVoiceClient (per-user buffers + push_audio)
	•	tests/test_respond.py uses fakes to assert persona injection and multimodal outputs
	•	tests/test_shitposts.py runs sample templates through FakeLLM to assert shape and content constraints
	•	tests/audio/ contains short .wav fixtures for VAD/chunking tests
	•	Use dpytest to test command handlers; all network calls stubbed with fakes

CI guidance
	•	Run tests with uv run --with pytest pytest -q in CI
	•	Do not include tests that hit real providers in CI
	•	Nightly smoke job (optional) that runs with real credentials in an isolated test guild; require manual opt-in for secrets

Deployment notes
	•	Dockerfile installs libopus and any native deps for voice processing
	•	Use secrets manager for provider keys
	•	Expose /status health endpoint and Prometheus metrics endpoint

⸻

README.md (example — README-driven development)

# Clanker9000

Clanker9000 is a Discord bot that combines AI chat, shitposting, memes, and optional voice transcription.

It is built as a **library-first SDK** with a thin Discord host, designed for clarity, testability, and iteration speed.

## Features
- Threaded AI chat (`/chat`)
- Text-to-speech (`/speak`) via ElevenLabs
- Shitposting & memes (`/shitpost`) — haikus, plays, one-liners, images
- Optional voice transcription (single VC session at a time)

## Architecture (TL;DR)
- `clanker/` — pure Python SDK (no Discord imports)
- `clanker_bot/` — Discord application glue
- Context-as-data for replay & debugging

## Quickstart
```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e .
uv run clanker_bot/main.py

Configuration

Set environment variables:
	•	DISCORD_TOKEN
	•	OPENAI_API_KEY
	•	ELEVENLABS_API_KEY

Provider selection is explicit (v1): OpenAI, Whisper, ElevenLabs.

Testing
	•	Unit tests use fakes, not mocks
	•	Discord commands tested via dpytest
	•	Audio logic tested with prerecorded fixtures

uv run --with pytest pytest

Voice sessions

Clanker9000 supports one active voice session at a time. If busy, it returns a friendly BUSY message.

Philosophy

Clanker9000 is intentionally simple. If a feature adds complexity without improving debuggability, it is deferred.

⸻

Have fun clanking 🤖

# Appendix: Quick checklist for maintainers
- [ ] Secrets in env / secret manager
- [ ] Persona YAMLs defined
- [ ] Fake providers updated for tests
- [ ] Manual smoke test in test guild
