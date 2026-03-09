# Quick Start Guide

Get Clanker9000 running in under 5 minutes.

## Prerequisites

| Requirement | Version | Check Command |
|-------------|---------|---------------|
| Python | 3.10+ | `python --version` |
| uv | Latest | `uv --version` |
| OpenAI API Key | - | Set `OPENAI_API_KEY` |
| Discord Bot Token | - | Set `DISCORD_TOKEN` |

### Install uv (if needed)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Setup Steps

### 1. Clone and Install

```bash
git clone <repository-url>
cd clanker9000
make setup
```

This installs all dependencies and sets up pre-commit hooks.

### 2. Configure Environment

Create a `.env` file or export variables:

```bash
# Required
export OPENAI_API_KEY="sk-your-key-here"
export DISCORD_TOKEN="your-discord-bot-token"

# Optional (for TTS)
export ELEVENLABS_API_KEY="your-elevenlabs-key"
```

### 3. Create Bot Configuration

Create `config.yaml` in the project root:

```yaml
providers:
  llm: openai
  stt: openai
  tts: elevenlabs  # Remove if not using TTS
  image: memegen

personas:
  - id: clanker
    display_name: Clanker9000
    system_prompt: |
      You are Clanker9000, a Discord bot.
      Be helpful but keep responses concise.
    tts_voice: "Rachel"

default_persona: clanker
```

### 4. Verify Installation

```bash
# Run tests (should all pass)
make check

# Run only unit tests (no API keys needed)
uv run pytest tests -m "not network"
```

### 5. Start the Bot

```bash
# Run with your config
CLANKER_CONFIG_PATH=./config.yaml python -m clanker_bot.main
```

## First-Time Usage

### Using the SDK Directly

```python
import asyncio
from clanker.models import Context, Persona, Message
from clanker.providers.openai.llm import OpenAILLM
from clanker.respond import respond

async def main():
    # 1. Create a persona
    persona = Persona(
        id="bot",
        display_name="My Bot",
        system_prompt="You are a helpful assistant.",
    )

    # 2. Build request context
    context = Context(
        request_id="test-001",
        persona=persona,
        history=[
            Message(role="user", content="What is 2 + 2?")
        ],
    )

    # 3. Create LLM provider
    llm = OpenAILLM(api_key="sk-...")

    # 4. Generate response
    response, audio = await respond(context, llm=llm)
    print(f"Bot: {response.content}")

asyncio.run(main())
```

### Discord Bot Commands

Once the bot is running and invited to your server:

| Command | Description |
|---------|-------------|
| `/chat <message>` | Chat with the bot |
| `/speak <message>` | Chat with TTS audio response |
| `/shitpost [n] [guidance]` | Generate meme previews (1-5, default 1) |
| `/join` | Join your voice channel for transcription |
| `/leave` | Leave the current voice channel |
| `/transcript` | Show recent voice transcripts (ephemeral) |

**Health Endpoint:** The bot exposes an HTTP health endpoint at `/status` (not a Discord command).

### Voice Features

To enable voice transcription:

1. Ensure `discord-ext-voice-recv` is installed (included in dependencies)
2. Bot needs "Connect" and "Speak" permissions in voice channels
3. Use the voice ingest feature to transcribe spoken audio

## Configuration Reference

### Provider Options

| Provider Type | Available Values |
|--------------|------------------|
| `llm` | `openai`, `anthropic` |
| `stt` | `openai` |
| `tts` | `elevenlabs` |
| `image` | `memegen` |

### Persona Fields

```yaml
personas:
  - id: unique-id           # Required: Unique identifier
    display_name: Bot Name  # Required: Display name
    system_prompt: |        # Required: LLM system prompt
      Your instructions here
    tts_voice: "Rachel"     # Optional: ElevenLabs voice name
    providers: {}           # Optional: Per-persona provider overrides
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes* | OpenAI API key for LLM/STT |
| `ANTHROPIC_API_KEY` | Yes* | Anthropic API key for LLM (if using `llm: anthropic`) |
| `DISCORD_TOKEN` | Yes | Discord bot token |
| `ELEVENLABS_API_KEY` | No | ElevenLabs API key for TTS |
| `CLANKER_CONFIG_PATH` | No | Path to config.yaml |
| `DATABASE_URL` | No | Database URL (default: `sqlite:///data/clanker.db`) |
| `VOICE_DEBUG` | No | Enable voice debug capture (`1` to enable) |
| `VOICE_DEBUG_DIR` | No | Debug output directory (default: `./voice_debug`) |

## Common Issues

### "ModuleNotFoundError: No module named 'clanker'"

Ensure you're running commands through `uv run`:

```bash
# Wrong
python -m clanker_bot.main

# Correct
uv run python -m clanker_bot.main
```

### "OPENAI_API_KEY not set"

Export the environment variable before running:

```bash
export OPENAI_API_KEY="sk-..."
uv run pytest tests -m network
```

### Tests Failing with Network Errors

Network tests require valid API keys. Run only unit tests:

```bash
uv run pytest tests -m "not network"
```

### Discord Bot Not Responding

1. Check bot has correct permissions in Discord Developer Portal
2. Verify `DISCORD_TOKEN` is set correctly
3. Ensure bot is invited to your server with proper scopes
4. Check logs for connection errors

### Voice Not Working

1. Install FFmpeg: `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux)
2. Ensure `libopus` is installed
3. Bot needs "Connect" permission in voice channels

## Next Steps

- [Architecture Overview](./ARCHITECTURE.md) - Understand the system design
- [Contributing Guide](./CONTRIBUTING.md) - Set up for development
- [Configuration Schema](config_schema.md) - Full configuration reference
