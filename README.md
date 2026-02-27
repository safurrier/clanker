# Clanker9000

SDK-first Discord bot with chat, voice pipeline, shitposts, and a standalone CLI.

Clanker9000 separates a reusable SDK (`clanker`) from its Discord host (`clanker_bot`). Build multi-personality bots with LLM chat, voice transcription, TTS output, and meme generation — all with pluggable provider abstractions. Use the SDK standalone via the CLI without any Discord infrastructure.

## Features

- **Multi-Persona Support** - YAML-configured bot personalities with custom system prompts and voice settings
- **Voice Pipeline** - Real-time voice activity detection (Silero VAD), chunking, idle flush, and speech-to-text
- **Voice Resilience** - Keepalive packets, automatic reconnection, and actor-based voice management
- **CLI Interface** - Chat, speak, transcribe, and generate memes from the command line
- **Provider Architecture** - Pluggable adapters for LLM (OpenAI), STT (Whisper), TTS (ElevenLabs), and image generation (Memegen)
- **Shitpost Generator** - Context-aware meme generation with ephemeral preview/post/regenerate workflow
- **VC Monitoring** - Auto-leave when alone, nudge-to-join when humans gather
- **Feedback Persistence** - Track user interactions (accepted/rejected/regenerated) with SQLite via sqlc
- **Structured Logging** - File-based rotation, JSON format, voice-specific log levels

## Discord Commands

| Command | Description |
|---------|-------------|
| `/chat <prompt>` | Chat with Clanker |
| `/speak <prompt>` | Chat with TTS audio response |
| `/shitpost [n] [guidance]` | Generate meme previews with Post/Regenerate/Dismiss buttons |
| `/join` | Join your voice channel for transcription |
| `/leave` | Leave the current voice channel |
| `/transcript` | Show recent voice transcripts (ephemeral) |
| `/admin_active_meetings` | List active voice meetings |
| `/admin_stop_new_meetings` | Prevent new voice meetings |
| `/admin_allow_new_meetings` | Allow new voice meetings |

## CLI Commands

```bash
clanker chat "What is the meaning of life?"    # Chat with the LLM
clanker speak "Hello world" -o hello.mp3       # Generate TTS audio
clanker transcribe audio.wav                   # Transcribe audio file
clanker shitpost --guidance "programming"       # Generate a shitpost
clanker meme --guidance "cats"                  # Generate a meme image
clanker config show                            # Show active configuration
```

Use `--config path/to/config.yaml` and `--persona <id>` to control persona selection.

## Installation

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

### Install from GitHub

```bash
# Install the CLI tool (lightweight — SDK + CLI only)
uv tool install git+https://github.com/safurrier/clanker.git

# Install as a library
uv pip install git+https://github.com/safurrier/clanker.git

# Install with Discord bot support
uv pip install "clanker9000[bot] @ git+https://github.com/safurrier/clanker.git"

# Install with everything (bot + voice)
uv pip install "clanker9000[bot,voice] @ git+https://github.com/safurrier/clanker.git"
```

### Local Development Setup

```bash
# Install all dependencies (including bot, voice, dev)
make setup

# Run quality checks
make check
```

### Environment Variables

```bash
# Required for LLM and STT
export OPENAI_API_KEY="sk-..."

# Required for Discord bot
export DISCORD_TOKEN="..."

# Required for TTS
export ELEVENLABS_API_KEY="..."

# Optional
export CLANKER_CONFIG_PATH="./config.yaml"   # Custom config path
export VOICE_DEBUG=1                          # Enable voice debug capture
export VOICE_DEBUG_DIR="./voice_debug"        # Debug output directory
export LOG_DIR="./logs"                       # Enable file logging (JSON, rotated)
export LOG_LEVEL="INFO"                       # Base log level
export VOICE_LOG_LEVEL="INFO"                 # Voice-specific log level
export DATABASE_URL="sqlite:///data/clanker.db"  # Database path
export USE_VOICE_ACTOR=1                      # Enable actor-based voice management
```

## Quick Start

### SDK Usage

```python
from clanker.models import Context, Message, Persona
from clanker.providers.openai.llm import OpenAILLM
from clanker.respond import respond

# Create a persona
persona = Persona(
    id="assistant",
    display_name="Helper",
    system_prompt="You are a helpful assistant.",
)

# Build context
context = Context(
    request_id="req-001",
    user_id=0,
    guild_id=None,
    channel_id=0,
    persona=persona,
    messages=[Message(role="user", content="Hello!")],
    metadata={},
)

# Generate response
llm = OpenAILLM(api_key="sk-...")
response, audio = await respond(context, llm=llm)
print(response.content)
```

### Voice Transcription

```python
from clanker.providers.openai.stt import OpenAISTT

stt = OpenAISTT(api_key="sk-...")

with open("audio.wav", "rb") as f:
    audio_bytes = f.read()

transcript = await stt.transcribe(audio_bytes)
print(transcript)
```

### Run the Discord Bot

Requires the `[bot]` extra (included by `make setup`):

```bash
make run

# Or directly:
python -m clanker_bot.main

# With custom config:
CLANKER_CONFIG_PATH=./my-config.yaml make run
```

## Configuration

Create a `config.yaml` file:

```yaml
providers:
  llm: openai
  stt: openai
  tts: elevenlabs
  image: memegen

personas:
  - id: clanker
    display_name: Clanker9000
    system_prompt: |
      You are Clanker9000, a witty and slightly sarcastic Discord bot.
      Keep responses concise and entertaining.
    tts_voice: "Rachel"

  - id: helper
    display_name: Helper Bot
    system_prompt: |
      You are a helpful assistant. Be clear and informative.
    tts_voice: "Alice"

default_persona: clanker
```

## Project Structure

```
src/
  clanker/                  # Core SDK (no Discord dependencies)
    config/                 # Configuration loading (YAML)
    providers/              # Pluggable provider adapters
      openai/               # LLM (GPT) and STT (Whisper)
      elevenlabs/           # TTS
      memegen/              # Meme image generation
      audio_utils.py        # Stereo-to-mono, resampling
      base.py               # Protocol definitions (LLM, STT, TTS, ImageGen)
      factory.py            # Provider construction with lazy env-var resolution
    shitposts/              # Template-based meme content generation
    voice/                  # Voice processing pipeline
      vad.py                # Voice activity detection (Silero/Energy)
      chunker.py            # Audio chunking with idle flush
      formats.py            # AudioFormat abstraction
      worker.py             # Transcription orchestration
      debug/                # Debug capture system
    models.py               # Domain models (Context, Persona, Message)
    respond.py              # Core response orchestration

  clanker_cli/              # Click-based CLI (consumes SDK)
    commands/               # chat, speak, transcribe, shitpost, meme, config
    main.py                 # CLI entry point and shared context

  clanker_bot/              # Discord bot host
    command_handlers/       # /chat, /speak, /shitpost, /join, /leave, etc.
    cogs/                   # Discord cogs (vc_monitor)
    persistence/            # Feedback persistence (sqlc-gen-python + SQLite)
    views/                  # Discord UI views (shitpost preview)
    voice_actor.py          # Actor-based voice management
    voice_ingest.py         # Voice receive integration
    voice_resilience.py     # Keepalive and reconnection
    logging_config.py       # Structured logging setup
    commands.py             # Slash command registration
    health.py               # Health endpoint
    main.py                 # Bot entry point

tests/                      # Test suite
  cli/                      # CLI command tests (CliRunner + fakes)
  network/                  # Integration tests (require API keys)
  test_*.py                 # Unit tests
```

## Development

```bash
make check    # Run all checks (lint, format, test, typecheck)
make test     # Run tests (excludes network tests)
make lint     # Ruff linting with auto-fix
make format   # Ruff formatting
make ty       # Type checking with ty
make setup    # Install all dependencies with uv
make run      # Run the Discord bot
```

### Voice Support

Voice features require additional dependencies:

```bash
uv pip install -e ".[voice]"
```

Two VAD implementations are available:

| Implementation | Accuracy | Dependencies | Size |
|----------------|----------|--------------|------|
| **SileroVAD** (default) | High (ML-based) | torch, numpy | ~500MB |
| **EnergyVAD** (fallback) | Moderate (RMS) | Built-in | Minimal |

## Docker

See `docker/README.md` for full documentation.

```bash
docker-compose up -d
```

## Documentation

Detailed guides in `agent_docs/`:
- [Architecture](agent_docs/architecture.md) - System design, data flows, design decisions
- [Testing](agent_docs/testing.md) - Testing strategy, fixtures, fakes, markers
- [Voice Pipeline](agent_docs/voice-pipeline.md) - End-to-end voice processing and debugging
- [Providers](agent_docs/providers.md) - Provider system and adding new providers

Additional docs in `docs/`:
- [Quick Start](docs/QUICKSTART.md)
- [Contributing](docs/CONTRIBUTING.md)
- [Configuration Schema](docs/config_schema.md)
- [Voice Debugging](docs/voice-debugging.md)

## License

MIT License - see LICENSE file for details.
