# Testing Guide

Comprehensive testing strategy for the Clanker codebase.

## Quick Reference

```bash
make test                                    # All tests except network
make check                                   # lint + format + test + typecheck
uv run pytest tests -m "not network"         # Same as make test
uv run pytest tests -m network -v            # Network tests only (needs API keys)
uv run pytest tests/cli/ -v                  # CLI tests only
uv run pytest tests/test_respond.py -v       # Single test file
uv run pytest tests -k "test_chat" -v        # Tests matching pattern
```

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures (persona, context, etc.)
├── fakes.py                 # Test fakes: FakeLLM, FakeSTT, FakeTTS, FakeImage
├── meme_scoring.py          # Meme quality scoring utilities
├── metrics.py               # Test metrics utilities
│
├── test_sanity.py           # Import and basic sanity checks
├── test_models.py           # Domain model tests
├── test_config.py           # Configuration loading/validation
├── test_respond.py          # Response orchestration
├── test_provider_factory.py # Provider factory tests
├── test_shitposts.py        # Shitpost generation
├── test_meme_pipeline.py    # Meme pipeline
│
├── test_voice_chunker.py    # Audio chunking
├── test_voice_worker.py     # Voice worker
├── test_voice_ingest.py     # Discord voice ingest
├── test_voice_resilience.py # Voice keepalive/reconnect
├── test_voice_actor.py      # Actor-based voice
├── test_audio_formats.py    # Audio format conversion
├── test_audio_utils.py      # Audio utilities
├── test_audio_e2e.py        # End-to-end audio pipeline
├── test_audio_scenarios.py  # Audio scenario tests
├── test_real_audio.py       # Real audio samples
├── test_debug_capture.py    # Debug capture system
│
├── test_commands.py         # Discord slash commands (dpytest)
├── test_dpytest_commands.py # dpytest command tests
├── test_admin_commands.py   # Admin commands
├── test_thread_chat.py      # Thread auto-reply
├── test_transcript_command.py # Transcript command
├── test_message_chunking.py # Message chunking
│
├── test_openai_adapters.py  # OpenAI adapter tests
├── test_memegen_adapter.py  # Memegen adapter tests
├── test_feedback_models.py  # Feedback models
├── test_feedback_protocol.py # Feedback protocol
├── test_sql_feedback.py     # SQL feedback store
│
├── test_logging.py          # Logging config
├── test_health.py           # Health endpoint
├── test_vc_monitor.py       # VC monitor cog
├── test_shitpost_preview_view.py # UI view
├── test_docs_setup.py       # Documentation setup
│
├── cli/                     # CLI-specific tests
│   ├── test_commands.py     # CliRunner + fakes (26 unit tests)
│   └── test_e2e.py          # Real API calls (18 tests, @pytest.mark.network)
│
├── network/                 # Network integration tests
│   ├── test_openai_smoke.py # OpenAI API smoke tests
│   └── test_memegen_smoke.py # Memegen API smoke tests
│
├── audio_fixtures/          # Audio fixture files
└── data/                    # Test data (LibriSpeech, AMI samples)
```

## Pytest Markers

| Marker | Purpose | Required Env |
|--------|---------|-------------|
| `network` | Tests hitting real APIs | `OPENAI_API_KEY` |
| `memegen` | Memegen API tests | None (public API) |
| `slow` | Long-running tests | None |

Configured in `pyproject.toml` under `[tool.pytest.ini_options]`.

## Test Fakes (`tests/fakes.py`)

Reusable test doubles that satisfy provider protocols:

### FakeLLM
```python
FakeLLM(reply_text="Hello")  # Returns Message(role="assistant", content="Hello")
```

### FakeSTT
```python
FakeSTT(transcript="hello world")  # Returns "hello world" for any audio
```

### FakeTTS
```python
FakeTTS(audio_bytes=b"fake-audio")  # Returns b"fake-audio" for any text
```

### FakeImage
```python
FakeImage()  # Returns mock image data
```

## CLI Testing Pattern

CLI tests use Click's `CliRunner` with patched providers:

```python
from click.testing import CliRunner
from clanker.cli.main import cli
from tests.fakes import FakeLLM, FakeSTT, FakeTTS

def _patch_factory(llm=None, stt=None, tts=None):
    """Patch ProviderFactory methods to return fakes."""
    llm = llm or FakeLLM()
    stt = stt or FakeSTT()
    tts = tts or FakeTTS()
    return (
        patch("clanker.providers.factory.ProviderFactory.get_llm", return_value=llm),
        patch("clanker.providers.factory.ProviderFactory.get_stt", return_value=stt),
        patch("clanker.providers.factory.ProviderFactory.get_tts", return_value=tts),
    )

def test_chat_basic(runner):
    p_llm, p_stt, p_tts = _patch_factory(FakeLLM(reply_text="Hi"))
    with p_llm, p_stt, p_tts:
        result = runner.invoke(cli, ["chat", "Hello"])
    assert result.exit_code == 0
    assert "Hi" in result.output
```

## Shared Fixtures (`tests/conftest.py`)

Key fixtures available to all tests:
- `persona` — default test persona
- `context` — default test context with persona and messages
- Standard pytest fixtures: `tmp_path`, `monkeypatch`, etc.

## Audio Test Data

Real audio samples for voice pipeline testing:

```bash
make download-test-audio  # Downloads LibriSpeech + AMI samples
```

- `tests/data/sample1_monologue.wav` — single speaker monologue
- `tests/data/sample2_paused.wav` — speech with pauses
- `tests/data/sample3_multispeaker.wav` — multiple speakers
- `tests/data/librispeech/` — LibriSpeech corpus samples
- `tests/data/ami/` — AMI meeting corpus samples

## Writing New Tests

1. Place unit tests in `tests/test_<module>.py`
2. Use fakes from `tests/fakes.py` for provider mocking
3. Mark network-dependent tests with `@pytest.mark.network`
4. Use `tmp_path` fixture for temporary files
5. Test error cases (missing env vars, invalid input, provider errors)
6. For CLI tests, use `CliRunner` and `_patch_factory()` pattern in `tests/cli/`
