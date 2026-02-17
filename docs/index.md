# Clanker9000

SDK-first Discord bot with chat, shitposts, and voice pipeline.

## Overview

Clanker9000 provides a clean separation between a reusable SDK (`clanker`) and a Discord bot host (`clanker_bot`). Build multi-personality bots with LLM chat, voice transcription, TTS output, and custom content generation.

## Features

- **Multi-Persona Support** - Define bot personalities via YAML config
- **Voice Pipeline** - Real-time VAD, chunking, and speech-to-text
- **Provider Architecture** - Pluggable LLM, STT, TTS, and image adapters
- **Shitpost Generator** - Template-based LLM content generation
- **Policy System** - Pluggable validation before response generation
- **Replay Logging** - JSONL audit trail for debugging
- **Feedback Persistence** - Track user interactions with sqlc-gen-python

## Quick Links

| Document | Description |
|----------|-------------|
| [Quick Start](QUICKSTART.md) | Get up and running in 5 minutes |
| [Architecture](ARCHITECTURE.md) | System design and components |
| [Contributing](CONTRIBUTING.md) | Development setup and guidelines |
| [Configuration](config_schema.md) | Full config reference |
| [Audio Capture](audio-capture.md) | Voice transcription pipeline (VAD, utterances, multi-speaker) |
| [Voice Debugging](voice-debugging.md) | Debug capture, analysis, and troubleshooting |
| [Transcript Examples](transcript-examples.md) | Real-world conversation output examples |
| [Meme Pipeline](meme-pipeline.md) | Curated meme generation system |
| [Container Setup](container-setup.md) | Docker development and deployment |
| [Future Work](FUTURE_WORK.md) | Planned improvements and roadmap |

## Installation

```bash
# Clone and install
git clone <repository-url>
cd clanker9000
make setup

# Set environment variables
export OPENAI_API_KEY="sk-..."
export DISCORD_TOKEN="..."

# Run the bot
python -m clanker_bot.main
```

## Project Structure

```
src/
├── clanker/              # Core SDK (reusable library)
│   ├── providers/        # LLM, STT, TTS adapters
│   ├── voice/            # Voice pipeline
│   └── shitposts/        # Content generation
│
└── clanker_bot/          # Discord bot host
    ├── command_handlers/ # Command implementations
    ├── persistence/      # Database layer (sqlc)
    ├── views/            # Discord UI views
    ├── commands.py       # Slash command registration
    └── voice_ingest.py   # Voice receive integration
```

## Development

```bash
make check   # Run all quality checks
make test    # Run tests only
make lint    # Linting
make format  # Code formatting
```
