# Clanker9000

SDK-first Discord bot with chat, shitposts, and voice pipeline.

Clanker9000 provides a clean separation between a reusable SDK (`clanker`) and a Discord bot host (`clanker_bot`). Build multi-personality bots with LLM chat, voice transcription, TTS output, and custom content generation—all with extensible provider abstractions.

## Features

- **Multi-Persona Support** - Define multiple bot personalities via YAML config, each with custom system prompts and voice settings
- **Voice Pipeline** - Real-time voice activity detection (Silero VAD), chunking, and speech-to-text transcription with idle flush for faster responses
- **Thread Auto-Reply** - Automatic conversation in bot-created threads without requiring slash commands
- **Provider Architecture** - Pluggable adapters for LLM (OpenAI), STT (Whisper), TTS (ElevenLabs), and image generation (Memegen)
- **Shitpost Generator** - Template-based LLM meme generation with preview/post/regenerate workflow
- **Voice Debug Capture** - Debug system for offline voice pipeline analysis (enable with `VOICE_DEBUG=1`)
- **Health Monitoring** - Built-in health endpoint with uptime and version tracking

## Commands

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

## Installation

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd clanker9000

# Install dependencies
make setup

# Run quality checks
make check
```

### Environment Variables

```bash
# Required for LLM and STT
export OPENAI_API_KEY="sk-..."

# Required for TTS (optional feature)
export ELEVENLABS_API_KEY="..."

# Discord bot token
export DISCORD_TOKEN="..."

# Optional: Custom config path
export CLANKER_CONFIG_PATH="./config.yaml"

# Optional: Voice debug capture (for pipeline analysis)
export VOICE_DEBUG=1
export VOICE_DEBUG_DIR="./voice_debug"
```

## Quick Start

### 1. Basic Chat Interaction

```python
from clanker.models import Context, Persona, Message
from clanker.providers.openai_llm import OpenAILLM
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
    persona=persona,
    history=[Message(role="user", content="Hello!")],
)

# Generate response
llm = OpenAILLM(api_key="sk-...")
response, audio = await respond(context, llm=llm)
print(response.content)
```

### 2. Voice Transcription

```python
from clanker.providers.openai_stt import OpenAISTT

stt = OpenAISTT(api_key="sk-...")

# Transcribe audio file
with open("audio.wav", "rb") as f:
    audio_bytes = f.read()

transcript = await stt.transcribe(audio_bytes)
print(transcript)
```

### 3. Run the Discord Bot

```bash
# With default configuration
python -m clanker_bot.main

# With custom config
CLANKER_CONFIG_PATH=./my-config.yaml python -m clanker_bot.main
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
├── clanker/              # Core SDK (reusable library)
│   ├── config/           # Configuration loading
│   ├── providers/        # LLM, STT, TTS, Image adapters
│   │   └── audio_utils.py  # Stereo-to-mono, resampling utilities
│   ├── shitposts/        # Template-based content generation
│   ├── voice/            # Voice processing pipeline
│   │   ├── vad.py        # Voice activity detection (Silero/Energy)
│   │   ├── chunker.py    # Audio chunking
│   │   ├── formats.py    # AudioFormat abstraction
│   │   ├── worker.py     # Transcription orchestration
│   │   └── debug/        # Debug capture system
│   ├── models.py         # Domain models (Context, Persona, Message)
│   └── respond.py        # Core response orchestration
│
├── clanker_bot/          # Discord bot host
│   ├── command_handlers/ # Command implementations
│   │   ├── chat.py       # /chat, /speak, /shitpost
│   │   ├── voice.py      # /join, /leave
│   │   ├── transcript.py # /transcript
│   │   ├── thread_chat.py # Thread auto-reply handler
│   │   └── admin.py      # Admin commands
│   ├── views/            # Discord UI views (shitpost preview)
│   ├── commands.py       # Slash command registration
│   ├── voice_ingest.py   # Voice receive integration
│   ├── health.py         # Health endpoint (/status HTTP)
│   └── main.py           # Bot entry point
│
└── tests/                # Test suite
    ├── network/          # Integration tests (requires API keys)
    └── ...               # Unit tests
```

## Documentation

- [Quick Start Guide](./docs/QUICKSTART.md) - Get up and running quickly
- [Architecture](./docs/ARCHITECTURE.md) - System design and components
- [Contributing](./docs/CONTRIBUTING.md) - Development setup and guidelines
- [Configuration Schema](./docs/config_schema.md) - Full config reference
- [Voice Pipeline](./docs/voice_ingest_pipeline.md) - Voice processing details
- [Voice Debugging](./docs/voice-debugging.md) - Debug capture and analysis

## Development

```bash
# Run all checks
make check

# Run tests only
make test

# Run linting
make lint

# Format code
make format

# Type checking
make ty
```

## License

MIT License - see LICENSE file for details.
