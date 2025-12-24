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
| Voice pipeline | `src/clanker/voice/*.py` |
| Discord commands | `src/clanker_bot/commands.py` |
| Configuration | `src/clanker/config/` |

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

See `DOCKER_DEPLOYMENT.md` for full documentation.

**Quick start:**
```bash
# Create .env with DISCORD_TOKEN and OPENAI_API_KEY
docker-compose up -d
```

The Dockerfile includes:
- Pre-downloaded Silero VAD model (no runtime downloads)
- Voice support (torch/numpy) pre-installed
- Optimized multi-stage build

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
Edit `src/clanker_bot/commands.py`, add to `register_commands()`.

### Add a new persona
Update `config.yaml` with new persona definition.

### Modify voice pipeline
Files in `src/clanker/voice/`:
- `vad.py` - Voice activity detection
- `chunker.py` - Audio chunking
- `worker.py` - Transcription orchestration

### Update dependencies
Edit `pyproject.toml`, then `uv sync`.
