# Agent Instructions

Context for AI agents working on this codebase. `CLAUDE.md` is a symlink to this file.

## Project Overview

**Clanker9000** is an SDK-first Discord bot with:
- Chat via LLM (OpenAI, Anthropic)
- Voice transcription (Whisper STT)
- Text-to-speech (ElevenLabs — implemented but not yet deployed)
- Shitpost generation (template-based LLM content)
- CLI interface (Click-based, Discord-free)

## Architecture

Three sibling packages:

| Package | Purpose | Discord Dependencies |
|---------|---------|---------------------|
| `src/clanker/` | Core SDK (reusable library) | None |
| `src/clanker_cli/` | Click-based CLI (consumes SDK) | None |
| `src/clanker_bot/` | Discord bot host (consumes SDK) | Yes |

This separation enables testing the SDK without Discord infrastructure and using it standalone via the CLI.

See `agent_docs/architecture.md` for detailed architecture diagrams and design decisions.

## Key Patterns

### Immutable Domain Models
All models use `@dataclass(frozen=True)`:
```python
@dataclass(frozen=True)
class Message:
    role: str
    content: str
```

### Protocol-Based Providers
Providers are defined as `Protocol` classes for loose coupling:
```python
class LLM(Protocol):
    async def generate(self, context: Context, messages: list[Message], params: dict | None = None) -> Message: ...
```

Available protocols: `LLM`, `StructuredLLM`, `STT`, `TTS`, `ImageGen` (all in `src/clanker/providers/base.py`).

### Async-First
All I/O operations are async. Use `httpx.AsyncClient` for HTTP.

### Factory Pattern
Providers are constructed via `ProviderFactory` (`src/clanker/providers/factory.py`) which lazily resolves API keys from environment variables.

## File Locations

| Component | Location |
|-----------|----------|
| Domain models | `src/clanker/models.py` |
| Response orchestration | `src/clanker/respond.py` |
| Provider protocols | `src/clanker/providers/base.py` |
| Provider factory | `src/clanker/providers/factory.py` |
| Provider errors | `src/clanker/providers/errors.py` |
| OpenAI LLM/STT | `src/clanker/providers/openai/` |
| ElevenLabs TTS | `src/clanker/providers/elevenlabs/` |
| Memegen image | `src/clanker/providers/memegen/` |
| Audio utilities | `src/clanker/providers/audio_utils.py` |
| Voice pipeline (SDK) | `src/clanker/voice/` |
| Shitpost/meme engine | `src/clanker/shitposts/` |
| Configuration | `src/clanker/config/` |
| CLI entry point | `src/clanker_cli/main.py` |
| CLI commands | `src/clanker_cli/commands/` |
| Discord bot entry | `src/clanker_bot/main.py` |
| Discord commands | `src/clanker_bot/commands.py` |
| Command handlers | `src/clanker_bot/command_handlers/` |
| Voice ingest (Discord) | `src/clanker_bot/voice_ingest.py` |
| Voice resilience | `src/clanker_bot/voice_resilience.py` |
| Voice actor | `src/clanker_bot/voice_actor.py` |
| Discord UI views | `src/clanker_bot/views/` |
| Discord cogs | `src/clanker_bot/cogs/` |
| Logging configuration | `src/clanker_bot/logging_config.py` |
| Persistence layer | `src/clanker_bot/persistence/` |
| SQL queries | `src/clanker_bot/persistence/db/queries/` |
| Generated queries | `src/clanker_bot/persistence/generated/` |

## Commands

```bash
make check    # Run all quality checks (lint, format, test, type check)
make test     # Run tests only (excludes network tests)
make lint     # Ruff linting with auto-fix
make format   # Ruff formatting
make ty       # Type checking with ty
make setup    # Install all dependencies with uv
make run      # Run the Discord bot
```

## Testing

See `agent_docs/testing.md` for the full testing guide.

- Unit tests: `tests/test_*.py`
- CLI tests: `tests/cli/test_commands.py` (CliRunner + fakes)
- CLI e2e tests: `tests/cli/test_e2e.py` (requires `OPENAI_API_KEY`, marked `@pytest.mark.network`)
- Network tests: `tests/network/` (require API keys, marked `@pytest.mark.network`)
- Test fakes: `tests/fakes.py` (`FakeLLM`, `FakeTTS`, `FakeSTT`, `FakeImage`)

Run without network tests:
```bash
uv run pytest tests -m "not network"
```

## Code Style

- **Line length**: 88 characters
- **Type hints**: Required on all functions
- **Linter/Formatter**: ruff
- **Type checker**: ty
- **Imports**: Module-level only, never inside functions

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | LLM and STT |
| `DISCORD_TOKEN` | For bot | Discord bot token |
| `ELEVENLABS_API_KEY` | Not yet deployed | Text-to-speech via ElevenLabs (implemented, not enabled) |
| `CLANKER_CONFIG_PATH` | No | Custom config path |
| `VOICE_DEBUG` | No | Enable voice debug capture (`1` to enable) |
| `VOICE_DEBUG_DIR` | No | Debug output directory (default: `./voice_debug`) |
| `LOG_DIR` | No | Directory for file logs (enables file logging when set) |
| `LOG_LEVEL` | No | Base log level (default: `INFO`) |
| `VOICE_LOG_LEVEL` | No | Voice-specific log level (default: `INFO`) |
| `USE_VOICE_ACTOR` | No | Enable actor-based voice management |

## Voice Processing

See `agent_docs/voice-pipeline.md` for the full voice pipeline documentation.

Two VAD implementations:

| Implementation | Accuracy | Dependencies | Size |
|----------------|----------|--------------|------|
| **SileroVAD** (default) | High (ML-based) | torch, numpy | ~500MB |
| **EnergyVAD** (fallback) | Moderate (RMS) | Built-in | Minimal |

Install voice support: `uv pip install -e ".[voice]"`

## Docker Deployment

See `docker/README.md` for full documentation.

```bash
docker-compose up -d
```

## Nested Agent Docs

Module-specific agent instructions for deeper context:

| Module | AGENTS.md | Purpose |
|--------|-----------|---------|
| `src/clanker_cli/` | [CLI AGENTS.md](src/clanker_cli/AGENTS.md) | Click CLI patterns, async bridge, testing |
| `src/clanker/voice/` | [Voice AGENTS.md](src/clanker/voice/AGENTS.md) | VAD, chunking, transcription pipeline |
| `src/clanker_bot/` | [Bot AGENTS.md](src/clanker_bot/AGENTS.md) | Discord integration, commands, voice ingest |

## Cross-Cutting Documentation

Detailed guides in `agent_docs/`:

| Document | Purpose |
|----------|---------|
| [architecture.md](agent_docs/architecture.md) | System architecture, data flows, design decisions |
| [testing.md](agent_docs/testing.md) | Testing strategy, fixtures, fakes, markers |
| [voice-pipeline.md](agent_docs/voice-pipeline.md) | End-to-end voice processing, debugging, audio formats |
| [providers.md](agent_docs/providers.md) | Provider system, adding new providers, factory pattern |

## Common Tasks

### Add a new slash command
1. Create handler function in `src/clanker_bot/command_handlers/` (or add to existing file)
2. Export from `command_handlers/__init__.py`
3. Register in `src/clanker_bot/commands.py` `register_commands()` function
4. Add tests in `tests/test_commands.py`

### Add a new CLI command
1. Create command file in `src/clanker_cli/commands/`
2. Import and register in `src/clanker_cli/main.py` via `cli.add_command()`
3. Add tests in `tests/cli/test_commands.py` using `CliRunner` + `_patch_factory()`

### Add a new persona
Update `config.yaml` with new persona definition.

### Add a new provider
1. Define protocol in `src/clanker/providers/base.py` (if new type)
2. Implement adapter (e.g., `src/clanker/providers/anthropic/llm.py`)
3. Register in `src/clanker/providers/factory.py`
4. Add test fake in `tests/fakes.py`
5. Add tests

### Modify voice pipeline
See `agent_docs/voice-pipeline.md` for the full guide.

### Update dependencies
Edit `pyproject.toml`, then `uv sync`. Note: bot-specific deps (discord.py, sqlalchemy, aiohttp, aiosqlite) are in the `[bot]` optional group. SDK and CLI deps are in base `dependencies`. `make setup` uses `--all-extras` so all groups are installed locally.

### Modify database queries (sqlc)
```bash
# After editing db/queries/*.sql files:
sqlc generate
python3 scripts/fix_sqlc_placeholders.py
uv run ruff check src/clanker_bot/persistence/generated/ --fix
uv run ruff format src/clanker_bot/persistence/generated/
```

See `src/clanker_bot/persistence/README.md` for details.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/test_audio_pipeline.py` | Test VAD and STT pipeline with real audio |
| `scripts/download_test_audio.py` | Download LibriSpeech/AMI test samples |
| `scripts/test_meme_pipeline.py` | Test meme generation pipeline |
| `scripts/generate_memes.py` | Generate memes |
| `scripts/validate_registry.py` | Validate provider registry |
| `scripts/analyze_voice_session.py` | Analyze voice debug sessions |
| `scripts/fix_sqlc_placeholders.py` | Fix sqlc-generated placeholder syntax |
| `scripts/sync_commands.py` | Sync Discord slash commands |
