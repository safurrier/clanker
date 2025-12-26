# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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

### Changed
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
