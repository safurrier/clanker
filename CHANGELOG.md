# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Voice pipeline `AudioFormat` abstraction for source-agnostic audio handling:
  - `AudioFormat` dataclass with `bytes_per_sample`, `bytes_to_ms()`, `ms_to_bytes()` helpers
  - `DISCORD_FORMAT` (stereo 48kHz), `SDK_FORMAT` (mono 48kHz), `WHISPER_FORMAT` (mono 16kHz)
  - `stereo_to_mono()` and `convert_pcm()` utilities for format conversion
  - SDK is now source-agnostic - expects mono PCM, bot layer handles Discord conversion
- Idle flush mechanism for faster voice transcription:
  - `idle_timeout_seconds` parameter (default 3.0s) flushes partial buffers after silence
  - Transcripts now appear within ~3 seconds of user stopping speech
  - `chunk_seconds` lowered from 10s to 7.5s for more responsive continuous speech
- Voice pipeline debug capture system:
  - Enable with `VOICE_DEBUG=1` environment variable
  - Captures all pipeline stages to `voice_debug/session_*/`
  - `scripts/analyze_voice_session.py` for offline session analysis
  - `docs/voice-debugging.md` comprehensive debugging guide

### Fixed
- **Voice transcription not working** - Discord delivers stereo 48kHz PCM but pipeline assumed mono, causing 2x timing errors and corrupted audio. Fixed by adding stereo-to-mono conversion at Discord boundary.
- **Slow/missing transcriptions** - Short utterances were never processed because 10s buffer threshold was never reached. Fixed with idle flush mechanism.

### Added (continued)
- Ephemeral preview workflow for `/shitpost` command:
  - `ShitpostPreviewView` with Post/Regenerate/Dismiss buttons
  - Ephemeral messages visible only to command invoker
  - Post button publishes meme to channel (single-use)
  - Regenerate button picks a new random template
  - Dismiss button removes the preview
  - Parallel generation of N memes (1-5, default 3)
  - `n` parameter for number of previews, `guidance` for optional topic
- Channel context extraction for memes:
  - Fetches last 10 messages from text channel for context
  - Voice transcript integration (preferred over text when available)
  - `TranscriptBuffer` class for storing rolling voice events per guild
- Context-aware shitpost/meme generation:
  - `ShitpostContext` model for rich input sources (user input, transcripts, messages)
  - `Utterance` protocol for duck-typed voice transcript compatibility
  - Configurable windowing: `max_messages`, `max_transcript_minutes`, `max_transcript_utterances`
  - Replaces simple `topic: str` parameter with flexible context model
- Voice-to-meme integration tests:
  - `tests/test_voice_to_meme.py`: E2E tests transcribing real audio then generating memes
  - `tests/meme_scoring.py`: LLM-based meme quality scoring (relevance, format, coherence)
  - `MemeScoreResponse` structured output model for guaranteed valid scoring
  - Validates `TranscriptEvent` compatibility with `ShitpostContext`
- Structured LLM outputs via Instructor library:
  - `StructuredLLM` protocol for guaranteed schema-compliant responses
  - `generate_structured()` method on `OpenAILLM` using Pydantic models
  - `MemeLines` model for type-safe meme text generation
  - Provider-agnostic design: same code pattern works with OpenAI, Anthropic, etc.
  - Automatic retries on validation failures
- Audio pipeline test tooling for debugging voice capture:
  - `scripts/download_test_audio.py`: Download LibriSpeech and AMI corpus samples
  - `scripts/test_audio_pipeline.py`: VAD detection and transcription accuracy reports
  - `scripts/test_meme_pipeline.py`: Full voice-to-meme pipeline with quality scoring reports
  - `tests/test_real_audio.py`: E2E tests with real speech (marked `@pytest.mark.network`)
  - `tests/metrics.py`: WER (Word Error Rate) calculation for transcription accuracy
  - `tests/data/README.md`: Documentation for test audio datasets
- Integration with uv for dependency management
- Modern Python development tools:
  - ruff for linting and formatting
  - ty for type checking
  - pytest with coverage reporting
- GitHub Actions workflow for automated testing
- Docker development environment improvements
- Local CI testing with act for running GitHub Actions workflows locally
- Fast debug workflow for iterative development
- Make targets: `act-install`, `ci-list`, `ci-local`, `ci-local-docs`, `ci-debug`, `ci-clean`
- Discord bot setup guide in `docs/CONTRIBUTING.md`:
  - Privileged Gateway Intents configuration
  - OAuth2 invite URL with precise bot permissions (311388392448)
  - Template OAuth invite URL for easy setup
  - Troubleshooting section for common setup issues
- Local development environment with Docker:
  - `make dev-env` for interactive development container
  - Pre-installed dependencies and Silero VAD model
  - Source code mounted for live editing

### Changed
- Switched to loguru for structured logging (replaced standard logging)
- Split command handlers into separate modules (`command_handlers/` directory):
  - `chat.py` for `/chat` and `/speak` commands
  - `voice.py` for `/join` and `/leave` commands
  - `admin.py` for admin commands
  - `messages.py` for `/shitpost` command
- Switched from pip/venv to uv for environment management
- Updated example code to pass ty type checking
- Modernized project structure and development workflow
- Updated Python version to 3.12

### Removed
- Legacy dependency management approach
- Outdated Docker configuration elements

### Fixed
- Type hints in example code to pass ty checks
- Docker environment management
- Development workflow and quality checks

## [0.1.0] - 2024-04-14
- Initial fork from eugeneyan/python-collab-template
- Added Docker environment management
- Setup package installation configuration
