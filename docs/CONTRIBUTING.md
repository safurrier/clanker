# Contributing Guide

Guidelines for contributing to Clanker9000.

## Development Setup

### 1. Fork and Clone

```bash
git clone git@github.com:YOUR_USERNAME/clanker9000.git
cd clanker9000
```

### 2. Install Dependencies

```bash
make setup
```

This will:
- Create a virtual environment with uv
- Install all dependencies (runtime + dev)
- Set up pre-commit hooks

### 3. Verify Setup

```bash
make check
```

All checks should pass before you start development.

## Discord Bot Setup

Before running the bot locally, you need to create a Discord application and bot.

### 1. Create Discord Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications/)
2. Click "New Application" and give it a name
3. Go to the "Bot" section in the left sidebar

### 2. Enable Privileged Gateway Intents

**This step is required - the bot will crash without it.**

In the "Bot" section, scroll down to "Privileged Gateway Intents" and enable:

- **Server Members Intent** - Required for member tracking
- **Message Content Intent** - Required for message processing

Click "Save Changes".

### 3. Get Your Bot Token

In the "Bot" section:

1. Click "Reset Token" (or "View Token" if available)
2. Copy the token - you'll need this for `DISCORD_TOKEN`
3. Keep this secret! Never commit it to git.

### 4. Generate OAuth2 Invite URL

Go to "OAuth2" → "URL Generator":

1. **Scopes**: Select `bot` and `applications.commands`
2. **Bot Permissions**: Enter `311388392448` in the permissions integer field, or select:

   | Category | Permission |
   |----------|------------|
   | General | View Channels |
   | Text | Send Messages, Send Messages in Threads, Create Public Threads |
   | Text | Embed Links, Attach Files, Read Message History, Use Slash Commands |
   | Voice | Connect, Speak |

3. Copy the generated URL at the bottom

### 5. Invite Bot to Test Server

1. Create a test Discord server (or use an existing one you control)
2. Open the OAuth2 URL from step 4 in your browser
3. Select your test server and authorize

## Local Development with Docker

The easiest way to run the bot locally is with Docker.

### 1. Set Up Environment

```bash
# Copy the environment template
cp docker/template.env docker/.env

# Edit with your credentials
# Required: DISCORD_TOKEN, OPENAI_API_KEY
# Optional: ELEVENLABS_API_KEY
```

### 2. Start Development Environment

```bash
# Start dev container and enter shell
make dev-env
```

This gives you an interactive shell with:
- All dependencies pre-installed
- Source code mounted (changes reflected immediately)
- Silero VAD model pre-downloaded

### 3. Run the Bot

Inside the container:

```bash
# Run the bot
python -m clanker_bot.main

# Or with custom config
CLANKER_CONFIG_PATH=./config.yaml python -m clanker_bot.main

# Run with debug logging
LOG_LEVEL=DEBUG python -m clanker_bot.main
```

### 4. Run Tests Inside Container

```bash
# Unit tests (no API keys needed)
pytest tests -m "not network"

# All checks
make check
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | Yes | Bot token from Developer Portal |
| `OPENAI_API_KEY` | Yes | OpenAI API key for LLM/STT |
| `ELEVENLABS_API_KEY` | No | ElevenLabs API key for TTS |
| `CLANKER_CONFIG_PATH` | No | Path to custom config.yaml |
| `LOG_LEVEL` | No | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Troubleshooting

**Bot crashes with `PrivilegedIntentsRequired`:**
- Go back to Developer Portal → Bot → Privileged Gateway Intents
- Enable both "Server Members Intent" and "Message Content Intent"
- Save changes and restart the bot

**Slash commands don't appear:**
- Commands sync on bot startup - wait a minute
- Try kicking and re-inviting the bot
- Check bot has "Use Slash Commands" permission

**Voice features not working:**
- Ensure bot has "Connect" and "Speak" permissions in the voice channel
- Check that FFmpeg is installed: `ffmpeg -version`

See `docker/README.md` for more Docker options.

## Code Standards

### Style Guide

We use [ruff](https://github.com/astral-sh/ruff) for linting and formatting:

- **Line length**: 88 characters
- **Python version**: 3.10+ features allowed
- **Import sorting**: Handled by ruff (isort rules)

### Type Hints

All code must have type hints. We use [ty](https://astral.sh/blog/ty) for type checking:

```python
# Good
def process_audio(audio_bytes: bytes, sample_rate: int = 48000) -> list[str]:
    ...

# Bad - missing types
def process_audio(audio_bytes, sample_rate=48000):
    ...
```

### Docstrings

Use docstrings for public functions and classes:

```python
def transcribe(self, audio_bytes: bytes, params: dict | None = None) -> str:
    """Transcribe audio bytes to text.

    Args:
        audio_bytes: Raw audio data in WAV format.
        params: Optional parameters for the transcription API.

    Returns:
        Transcribed text string.

    Raises:
        TransientProviderError: For retryable API errors (429, 5xx).
        PermanentProviderError: For non-retryable errors.
    """
```

### Immutable Data Classes

Domain models should be immutable:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Message:
    role: str
    content: str
```

### Async by Default

All I/O operations should be async:

```python
# Good
async def fetch_data(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()

# Bad - blocking I/O
def fetch_data(url: str) -> dict:
    response = requests.get(url)
    return response.json()
```

## Workflow

### Branch Strategy

```
main              # Production-ready code
└── feature/*     # New features
└── fix/*         # Bug fixes
└── refactor/*    # Code improvements
```

### Creating a Branch

```bash
# Feature
git checkout -b feature/add-new-provider

# Bug fix
git checkout -b fix/voice-chunking-edge-case

# Refactor
git checkout -b refactor/simplify-config-loader
```

### Commit Guidelines

Write clear, descriptive commit messages:

```bash
# Good
git commit -m "feat: add ElevenLabs TTS provider"
git commit -m "fix: handle empty audio buffer in voice pipeline"
git commit -m "refactor: extract VAD logic into separate module"
git commit -m "test: add coverage for persona serialization"
git commit -m "docs: update configuration examples"

# Bad
git commit -m "fix stuff"
git commit -m "WIP"
git commit -m "changes"
```

### Before Committing

Pre-commit hooks run automatically, but you can run manually:

```bash
make check
```

This runs:
1. `ruff check --fix` - Linting with auto-fix
2. `ruff format` - Code formatting
3. `pytest` - Full test suite
4. `ty check` - Type checking

## Testing

### Running Tests

```bash
# All tests
make test

# Unit tests only (no API keys needed)
uv run pytest tests -m "not network"

# Specific test file
uv run pytest tests/test_models.py -v

# Specific test function
uv run pytest tests/test_models.py::test_context_serialization -v

# With coverage report
uv run pytest tests --cov=clanker --cov-report=html
```

### Test Markers

| Marker | Description |
|--------|-------------|
| `@pytest.mark.network` | Requires network/API access |
| `@pytest.mark.slow` | Long-running test |
| `@pytest.mark.asyncio` | Async test function |

### Writing Tests

Place tests in `tests/` mirroring the source structure:

```
src/clanker/providers/openai_llm.py
tests/test_openai_adapters.py

src/clanker/voice/chunker.py
tests/test_voice_chunker.py
```

Use the provided test fakes:

```python
from tests.fakes import FakeLLM, FakeTTS

async def test_respond_with_fake_llm():
    llm = FakeLLM(response="Hello!")
    response, audio = await respond(context, llm=llm)
    assert response.content == "Hello!"
```

### Test Coverage

Maintain high coverage (currently ~90%):

```bash
# View coverage report
uv run pytest tests --cov=clanker --cov-report=term-missing
```

## Pull Request Process

### 1. Create PR

```bash
git push -u origin feature/your-feature
```

Then create PR on GitHub.

### 2. PR Checklist

Before requesting review:

- [ ] All tests pass (`make check`)
- [ ] New code has tests
- [ ] Type hints added for new code
- [ ] Docstrings for public APIs
- [ ] No linting errors
- [ ] Commit messages are clear

### 3. PR Description Template

```markdown
## Summary
Brief description of changes.

## Changes
- Added X
- Fixed Y
- Updated Z

## Testing
How was this tested?

## Notes
Any additional context.
```

### 4. Review Process

- PRs require at least one approval
- CI must pass (linting, tests, type checking)
- Address review comments with new commits

### 5. Merging

After approval:
- Squash and merge for feature branches
- Rebase and merge for clean history

## Project Structure

When adding new code, follow the existing structure:

```
src/
├── clanker/                 # SDK (reusable library)
│   ├── config/              # Configuration loading
│   ├── policies/            # Validation policies
│   ├── providers/           # Provider adapters
│   │   ├── __init__.py      # Public exports
│   │   ├── llm.py           # Protocol definition
│   │   └── openai_llm.py    # Implementation
│   ├── shitposts/           # Content generation
│   └── voice/               # Voice pipeline
│
├── clanker_bot/             # Discord bot host
│   └── ...
│
└── tests/
    ├── network/             # Integration tests
    ├── fakes.py             # Test doubles
    └── test_*.py            # Unit tests
```

### Adding a New Provider

1. Define protocol in `providers/` (if new type)
2. Implement adapter (e.g., `providers/anthropic_llm.py`)
3. Register in `providers/factory.py`
4. Add tests in `tests/test_*.py`
5. Update documentation

## Getting Help

- Check existing issues and PRs
- Open an issue for bugs or feature requests
- Discuss major changes before implementation
