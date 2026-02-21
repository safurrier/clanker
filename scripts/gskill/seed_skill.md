# Clanker SDK Developer Skill

A guide for AI coding agents working in the Clanker9000 Discord bot SDK.

## Running Tests

Run unit tests excluding network tests:

```bash
uv run pytest tests -m "not network"
```

Or use the Makefile:

```bash
make test       # unit tests only
make check      # lint + format + type check + tests
```

Network tests require API keys and are tagged `@pytest.mark.network`. Never run
them unless `OPENAI_API_KEY` is set.

## Project Layout

```
src/clanker/           Core SDK — no Discord dependency
  cli/                 Click-based CLI
    main.py            CLI entry point, CliContext, run_async()
    commands/          One file per command group (chat.py, shitpost.py, …)
    output.py          output_text(), output_json(), write_audio()
  providers/
    base.py            Protocol definitions: LLM, STT, TTS, ImageGen, StructuredLLM
    factory.py         ProviderFactory — registry + lazy construction
    errors.py          TransientProviderError, PermanentProviderError
    openai/            OpenAILLM, OpenAISTT adapters
    elevenlabs/        ElevenLabsTTS adapter
    memegen/           MemegenImage adapter
  models.py            Frozen dataclasses: Message, Context, Persona, Interaction
  respond.py           respond(context, llm, tts=None) → (Message, bytes|None)
src/clanker_bot/       Discord bot — builds on top of the SDK
tests/
  fakes.py             FakeLLM, FakeSTT, FakeTTS, FakeImage
  cli/
    test_commands.py   CLI command tests using CliRunner + _patch_factory()
```

## Adding a CLI Command

**Step 1 — create `src/clanker/cli/commands/<name>.py`:**

```python
"""<name> command."""

from __future__ import annotations

import click

from ...providers.errors import PermanentProviderError, TransientProviderError
from ...respond import respond
from ..main import CliContext, build_cli_context, read_prompt, run_async
from ..output import output_text


@click.command()
@click.argument("prompt", required=False)
@click.pass_obj
def <name>(ctx: CliContext, prompt: str | None) -> None:
    """Short description."""
    run_async(_<name>(ctx, prompt))


async def _<name>(ctx: CliContext, prompt: str | None) -> None:
    text = read_prompt(prompt)
    context = build_cli_context(ctx.persona, text)
    llm = ctx.factory.get_llm("openai")
    try:
        reply, _ = await respond(context, llm)
    except (TransientProviderError, PermanentProviderError) as exc:
        raise click.ClickException(str(exc)) from exc
    output_text(reply.content)
```

**Step 2 — register in `src/clanker/cli/main.py`** (at the bottom of the file):

```python
from .commands.<name> import <name>  # noqa: E402
cli.add_command(<name>)
```

The `run_async()` helper bridges async functions to Click's synchronous
command model. Always use it; never call `asyncio.run()` directly.

## Testing a CLI Command

In `tests/cli/test_commands.py`:

```python
from click.testing import CliRunner
from clanker.cli.main import cli
from tests.fakes import FakeLLM, FakeSTT, FakeTTS


def _patch_factory(llm=None, stt=None, tts=None):
    from unittest.mock import patch
    llm = llm or FakeLLM()
    stt = stt or FakeSTT()
    tts = tts or FakeTTS()
    return (
        patch("clanker.providers.factory.ProviderFactory.get_llm", return_value=llm),
        patch("clanker.providers.factory.ProviderFactory.get_stt", return_value=stt),
        patch("clanker.providers.factory.ProviderFactory.get_tts", return_value=tts),
    )


class Test<Name>:
    def test_<name>_basic(self, runner: CliRunner) -> None:
        p_llm, p_stt, p_tts = _patch_factory(FakeLLM(reply_text="ok"))
        with p_llm, p_stt, p_tts:
            result = runner.invoke(cli, ["<name>", "hello"])
        assert result.exit_code == 0
        assert "ok" in result.output

    def test_<name>_no_prompt(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["<name>"])
        assert result.exit_code != 0
```

`FakeLLM(reply_text="…")` returns a deterministic response without hitting
the network. Always use fakes in unit tests.

## Key Domain Models

```python
@dataclass(frozen=True)
class Message:
    role: str      # "user" | "assistant" | "system"
    content: str

@dataclass(frozen=True)
class Context:
    request_id: str
    user_id: int
    guild_id: int | None
    channel_id: int
    persona: Persona
    messages: list[Message]
    metadata: dict
```

Build a CLI context with `build_cli_context(persona, prompt_text)`.

## Adding a Provider

1. Create `src/clanker/providers/<name>/llm.py` implementing the `LLM` protocol:

```python
class <Name>LLM:
    def __init__(self, api_key: str) -> None: ...
    async def generate(self, context: Context, messages: list[Message], params: dict | None = None) -> Message: ...
```

2. Register in `src/clanker/providers/factory.py`:

```python
from .<name> import <Name>LLM

# inside ProviderFactory.__init__:
self._llm_registry["<name>"] = lambda: <Name>LLM(api_key=_require_env("<NAME>_API_KEY"))
```

`_require_env(key)` raises `ValueError` with a helpful message if the env var
is missing.

## Key Patterns

- **Immutable models**: all domain models are `@dataclass(frozen=True)`
- **Protocol-based providers**: use `typing.Protocol` — no base classes
- **Async-first**: all I/O is async; CLI bridges with `run_async()`
- **Provider errors**: always catch `TransientProviderError` and
  `PermanentProviderError` at the command boundary
- **Imports**: module-level only; never inside functions
