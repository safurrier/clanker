# CLI Module — Agent Instructions

Click-based CLI for the Clanker SDK. Provides all SDK capabilities (chat, speak, transcribe, shitpost, meme) from the terminal without Discord.

## Command Tree

```
clanker [--config PATH] [--persona ID] [--verbose]
├── chat <prompt>               # LLM chat, text response
├── speak <prompt>              # LLM chat + TTS, writes audio file
├── transcribe <audio-file>     # STT from audio file (WAV)
├── shitpost [topic]            # Template-based LLM content
├── meme [topic]                # Meme text + memegen URL
└── config
    ├── show                    # Dump resolved config
    ├── validate <path>         # Validate a config YAML
    └── personas                # List personas
```

## File Structure

```
cli/
├── __init__.py          # Exports: cli
├── main.py              # Click group, CliContext, async bridge, persona/config resolution
├── output.py            # output_text(), output_json(), write_audio() helpers
└── commands/
    ├── __init__.py
    ├── chat.py          # chat + speak commands
    ├── shitpost.py      # shitpost + meme commands
    ├── transcribe.py    # transcribe command
    └── config_cmd.py    # config subgroup (show/validate/personas)
```

## Key Patterns

### CliContext (shared state)

```python
@dataclass
class CliContext:
    config: ClankerConfig | None
    factory: ProviderFactory
    persona: Persona
    verbose: bool
```

Created once in the top-level `@click.group()` callback, passed to subcommands via `@click.pass_obj`. Providers are constructed lazily in each command so `clanker config show` doesn't require API keys.

### Async Bridge

All SDK I/O is async. Each command calls `run_async()` on an async implementation function:

```python
@click.command()
@click.pass_obj
def chat(ctx: CliContext, prompt: str, ...) -> None:
    run_async(_chat(ctx, prompt, ...))
```

`run_async()` (in `main.py`) wraps `asyncio.run()` and drains background tasks before loop exit to avoid `CancelledError` noise from `respond()`'s fire-and-forget replay logging.

### Stdin Support

`chat` and `speak` accept prompt as positional arg or piped via stdin:
```bash
clanker chat "What is life?"
echo "Explain Python" | clanker chat
```

Implemented via `read_prompt()` in `main.py`.

### Error Handling

- `ValueError` from `_require_env()` in factory.py → `click.ClickException` with actionable message
- `TransientProviderError` / `PermanentProviderError` → `click.ClickException`
- Never show tracebacks to users

## Adding a New CLI Command

1. Create `src/clanker/cli/commands/new_cmd.py`
2. Define the command with `@click.command()` and `@click.pass_obj`
3. Use `run_async()` for async operations
4. Import and register in `main.py`: `cli.add_command(new_cmd)`
5. Add tests in `tests/cli/test_commands.py`

## Testing

Tests use Click's `CliRunner` with `_patch_factory()` that patches `ProviderFactory` methods to return fakes from `tests/fakes.py`:

```python
def _patch_factory(llm=None, stt=None, tts=None):
    llm = llm or FakeLLM()
    stt = stt or FakeSTT()
    tts = tts or FakeTTS()
    return (
        patch("clanker.providers.factory.ProviderFactory.get_llm", return_value=llm),
        patch("clanker.providers.factory.ProviderFactory.get_stt", return_value=stt),
        patch("clanker.providers.factory.ProviderFactory.get_tts", return_value=tts),
    )
```

- Unit tests: `tests/cli/test_commands.py` (26 tests, no API keys needed)
- E2E tests: `tests/cli/test_e2e.py` (18 tests, marked `@pytest.mark.network`, require `OPENAI_API_KEY`)

## Gotchas

- `transcribe` reads raw PCM from WAV but wraps it back in a WAV container before sending to STT (OpenAI expects WAV format)
- `meme` URL construction uses `quote(line, safe="")` to escape slashes in memegen path segments
- `run_async()` must be used instead of bare `asyncio.run()` to avoid CancelledError from background tasks
- `CliRunner` provides non-tty stdin, so `read_prompt()` checks for empty string after reading
