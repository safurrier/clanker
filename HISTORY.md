# Project History

Development timeline for Clanker9000, preserved before squashing to a clean initial commit.

## Timeline

**Dec 22, 2025 - Feb 17, 2026** | 22 PRs merged to main

## Development Phases

### Phase 1: Foundation (Dec 22, 2025)
- Initial codebase with SDK-first architecture (`clanker` SDK + `clanker_bot` Discord host)
- Domain models, provider protocols (LLM, STT, TTS), OpenAI and ElevenLabs adapters
- Basic `/chat`, `/speak`, `/join`, `/leave` Discord commands
- Code quality reviews and refactoring (PRs #1, #2)

### Phase 2: Command Structure (Dec 2025)
- Split monolithic command handlers into domain modules (`command_handlers/` directory) (PR #6)

### Phase 3: Meme Pipeline (Dec 2025 - Jan 2026)
- Curated meme pipeline with template-based generation via Memegen (PR #7)
- Context-aware shitpost generation using channel messages and voice transcripts (PR #10)
- Ephemeral preview workflow with Post/Regenerate/Dismiss buttons (PR #11)
- Structured LLM outputs via Instructor library for type-safe meme text

### Phase 4: Voice Pipeline (Jan 2026)
- Voice activity detection with Silero VAD (ML-based) and Energy VAD (fallback)
- Audio chunking, stereo-to-mono conversion, `AudioFormat` abstraction (PR #8)
- Idle flush mechanism for faster transcription (PR #13)
- Audio pipeline test tooling with LibriSpeech/AMI corpus samples (PR #9)
- Voice debug capture system for offline pipeline analysis

### Phase 5: Monitoring & Resilience (Jan - Feb 2026)
- VC monitoring cog: auto-leave when alone, nudge-to-join when humans gather (PR #15)
- Enhanced logging: file-based rotation, JSON format, voice-specific log levels
- Voice connection resilience: keepalive packets, automatic reconnection (PR #18, #19)
- Actor-based voice management behind feature flag (PR #20)

### Phase 6: Persistence (Feb 2026)
- Feedback persistence layer with sqlc-gen-python (PR #16)
- Interaction tracking: accepted/rejected/regenerated/timeout outcomes
- User preferences aggregation from interaction history

### Phase 7: CLI (Feb 2026)
- Click-based CLI for Discord-free SDK usage (PR #21)
- Commands: `clanker chat`, `speak`, `transcribe`, `shitpost`, `meme`, `config`
- Async bridge for running SDK coroutines from synchronous Click handlers
- CliRunner-based test suite with provider fakes

## Architecture Evolution

The project started as an SDK-first design from day one, with a clear separation between:
- **`src/clanker/`** - Core SDK with no Discord dependencies
- **`src/clanker_bot/`** - Discord-specific integration layer

This enabled the CLI (Phase 7) to be built entirely on the SDK without any Discord infrastructure.

## Key Technical Decisions

- **Protocol-based providers** over abstract base classes for loose coupling
- **Immutable dataclasses** (`frozen=True`) for all domain models
- **Factory pattern** with lazy env-var resolution for provider construction
- **sqlc-gen-python** for type-safe database queries (not an ORM)
- **Silero VAD** as primary voice detection with Energy VAD as zero-dependency fallback

## Contributors

Built with AI-assisted development using Claude Code and Codex.
