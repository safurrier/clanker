# Agent Instructions

Context for AI agents working on this codebase.

## Project Overview

**Clanker9000** is an SDK-first Discord bot with:
- Chat via LLM (OpenAI)
- Voice transcription (Whisper STT)
- Text-to-speech (ElevenLabs)
- Shitpost generation (template-based LLM content)

## Architecture

Two main packages:

| Package | Purpose | Discord Dependencies |
|---------|---------|---------------------|
| `src/clanker/` | Core SDK (reusable library) | None |
| `src/clanker_bot/` | Discord bot host | Yes |

This separation enables testing the SDK without Discord infrastructure.

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

### Async-First
All I/O operations are async. Use `httpx.AsyncClient` for HTTP.

## File Locations

| Component | Location |
|-----------|----------|
| Domain models | `src/clanker/models.py` |
| Response orchestration | `src/clanker/respond.py` |
| Provider protocols | `src/clanker/providers/*.py` |
| Voice pipeline (SDK) | `src/clanker/voice/*.py` |
| Voice ingest (Discord) | `src/clanker_bot/voice_ingest.py` |
| Discord command registration | `src/clanker_bot/commands.py` |
| Command handlers | `src/clanker_bot/command_handlers/` |
| Discord UI views | `src/clanker_bot/views/` |
| Discord cogs | `src/clanker_bot/cogs/` |
| Logging configuration | `src/clanker_bot/logging_config.py` |
| Configuration | `src/clanker/config/` |
| Persistence layer | `src/clanker_bot/persistence/` |
| SQL queries | `src/clanker_bot/persistence/db/queries/` |
| Generated queries | `src/clanker_bot/persistence/generated/` |

## Commands

```bash
make check    # Run all quality checks (lint, format, test, type check)
make test     # Run tests only
make lint     # Ruff linting with auto-fix
make format   # Ruff formatting
make ty       # Type checking with ty
```

## Testing

- Unit tests: `tests/test_*.py`
- Network tests: `tests/network/` (require API keys, marked with `@pytest.mark.network`)
- Test fakes: `tests/fakes.py` (FakeLLM, FakeTTS, etc.)

Run without network tests:
```bash
uv run pytest tests -m "not network"
```

## Code Style

- **Line length**: 88 characters
- **Type hints**: Required on all functions
- **Linter/Formatter**: ruff
- **Type checker**: ty

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | LLM and STT |
| `DISCORD_TOKEN` | For bot | Discord bot token |
| `ELEVENLABS_API_KEY` | For TTS | Text-to-speech |
| `CLANKER_CONFIG_PATH` | No | Custom config path |
| `VOICE_DEBUG` | No | Enable voice debug capture (`1` to enable) |
| `VOICE_DEBUG_DIR` | No | Debug output directory (default: `./voice_debug`) |
| `LOG_DIR` | No | Directory for file logs (enables file logging when set) |
| `LOG_LEVEL` | No | Base log level (default: `INFO`) |
| `VOICE_LOG_LEVEL` | No | Voice-specific log level (default: `INFO`) |

## Voice Processing with VAD

Two voice activity detection (VAD) implementations:

| Implementation | Accuracy | Dependencies | Size |
|----------------|----------|--------------|------|
| **SileroVAD** (default) | High (ML-based) | torch, numpy | ~500MB |
| **EnergyVAD** (fallback) | Moderate (RMS) | Built-in | Minimal |

**Install voice support:**
```bash
uv pip install -e ".[voice]"
```

**Warmup on bot startup** (recommended):
```python
from clanker_bot.voice_ingest import warmup_voice_detector

# Pre-load Silero VAD model
detector = await warmup_voice_detector(prefer_silero=True)
```

The warmup function validates dependencies, loads the model, and falls back gracefully to EnergyVAD if Silero is unavailable.

## Docker Deployment

See `docker/README.md` for full documentation.

**Quick start:**
```bash
# Create .env with DISCORD_TOKEN and OPENAI_API_KEY
docker-compose up -d
```

The Dockerfile includes:
- **libopus** for Discord audio decoding (required for voice)
- Pre-downloaded Silero VAD model (no runtime downloads)
- Voice support (torch/numpy) pre-installed
- Optimized multi-stage build

The bot explicitly loads opus at startup and fails fast if unavailable.

## Audio Pipeline Debugging

Scripts for testing and debugging the voice capture pipeline with real audio:

```bash
# Download LibriSpeech and AMI test samples
make download-test-audio

# Test VAD detection only (no API key required)
python scripts/test_audio_pipeline.py

# Full STT test with transcription accuracy metrics
export OPENAI_API_KEY=sk-...
python scripts/test_audio_pipeline.py --stt
```

The `scripts/test_audio_pipeline.py` script reports:
- VAD segment detection (Silero vs Energy comparison)
- Speech-to-text accuracy (WER - Word Error Rate)
- Multi-speaker handling (AMI corpus)

Useful for diagnosing issues like missed speech segments, poor transcription, or VAD threshold tuning.

See `tests/data/README.md` for detailed test data documentation.

## Adding New Providers

1. Define protocol in `providers/` (if new type)
2. Implement adapter (e.g., `providers/anthropic_llm.py`)
3. Register in `providers/factory.py`
4. Add tests

## Reference Materials

Additional context in `ai-docs/`:
- `clanker.md` - Original design document
- `ExecPlan.md` - Implementation plan and progress

## Common Tasks

### Add a new slash command
1. Create handler function in `src/clanker_bot/command_handlers/` (or add to existing file)
2. Export from `command_handlers/__init__.py`
3. Register in `src/clanker_bot/commands.py` `register_commands()` function
4. Add tests in `tests/test_commands.py`

### Add a new persona
Update `config.yaml` with new persona definition.

### Modify voice pipeline
SDK layer (`src/clanker/voice/`):
- `formats.py` - AudioFormat abstraction (`DISCORD_FORMAT`, `SDK_FORMAT`, `WHISPER_FORMAT`)
- `vad.py` - Voice activity detection (Silero/Energy)
- `chunker.py` - Audio chunking
- `worker.py` - Transcription orchestration
- `debug/` - Debug capture system (enable with `VOICE_DEBUG=1`)

Discord layer (`src/clanker_bot/`):
- `voice_ingest.py` - Discord audio capture, stereo-to-mono conversion, buffering, async processing

Audio utilities (`src/clanker/providers/audio_utils.py`):
- `stereo_to_mono()` - Convert stereo PCM to mono
- `convert_pcm()` - Convert between AudioFormat types
- `resample_pcm()` - Resample PCM to different sample rates

### Update dependencies
Edit `pyproject.toml`, then `uv sync`.

### Modify database queries (sqlc)
SQL queries use sqlc-gen-python for type-safe generated code:

```bash
# After editing db/queries/*.sql files:
sqlc generate
python3 scripts/fix_sqlc_placeholders.py
uv run ruff check src/clanker_bot/persistence/generated/ --fix
uv run ruff format src/clanker_bot/persistence/generated/
```

See `src/clanker_bot/persistence/README.md` for details.
