"""CLI entry point and shared context."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import click

from ..config import ClankerConfig, PersonaConfig, load_config
from ..models import Context, Message, Persona
from ..providers.factory import ProviderFactory

_T = TypeVar("_T")


@dataclass
class CliContext:
    """Shared state passed to subcommands via ``click.pass_obj``."""

    config: ClankerConfig | None
    factory: ProviderFactory
    persona: Persona
    verbose: bool


def _resolve_config(config_path: str | None) -> ClankerConfig | None:
    """Load config from explicit path or CLANKER_CONFIG_PATH env var."""
    path = config_path or os.getenv("CLANKER_CONFIG_PATH")
    if path:
        return load_config(Path(path))
    return None


def _resolve_persona(config: ClankerConfig | None, persona_id: str | None) -> Persona:
    """Resolve a Persona from config or return a sensible default."""
    if config:
        target_id = persona_id or config.default_persona_id
        for persona_cfg in config.personas:
            if persona_cfg.id == target_id:
                return _persona_from_config(persona_cfg)
        available = [p.id for p in config.personas]
        raise click.ClickException(
            f"Persona '{target_id}' not found. Available: {', '.join(available)}"
        )
    return Persona(
        id="default",
        display_name="Clanker",
        system_prompt="You are Clanker9000, a helpful assistant.",
    )


def _persona_from_config(cfg: PersonaConfig) -> Persona:
    return Persona(
        id=cfg.id,
        display_name=cfg.display_name,
        system_prompt=cfg.system_prompt,
        tts_voice=cfg.tts_voice,
        providers=cfg.providers,
    )


def build_cli_context(persona: Persona, prompt: str) -> Context:
    """Build an SDK Context for CLI usage."""
    return Context(
        request_id=str(uuid.uuid4()),
        user_id=0,
        guild_id=None,
        channel_id=0,
        persona=persona,
        messages=[Message(role="user", content=prompt)],
        metadata={"source": "cli"},
    )


def run_async(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run an async coroutine, draining background tasks before exit.

    ``respond()`` fires a background ``asyncio.create_task`` for replay
    logging.  A bare ``asyncio.run()`` cancels pending tasks on shutdown,
    producing noisy ``CancelledError`` tracebacks.  This wrapper gives
    those tasks a chance to finish cleanly.
    """

    async def _wrapper() -> _T:
        result = await coro
        # Let fire-and-forget tasks (e.g. replay log) finish
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        return result

    return asyncio.run(_wrapper())


def read_prompt(prompt: str | None) -> str:
    """Read prompt from argument or stdin."""
    if prompt:
        return prompt
    stdin_text = click.get_text_stream("stdin")
    if not stdin_text.isatty():
        text = stdin_text.read().strip()
        if text:
            return text
    raise click.UsageError("Provide a prompt as an argument or via stdin.")


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to config YAML (or set CLANKER_CONFIG_PATH).",
)
@click.option(
    "--persona",
    "persona_id",
    default=None,
    help="Persona ID to use.",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.pass_context
def cli(
    ctx: click.Context,
    config_path: str | None,
    persona_id: str | None,
    verbose: bool,
) -> None:
    """Clanker SDK command-line interface."""
    config = _resolve_config(config_path)
    persona = _resolve_persona(config, persona_id)
    ctx.obj = CliContext(
        config=config,
        factory=ProviderFactory(),
        persona=persona,
        verbose=verbose,
    )


# Register subcommands
from .commands.chat import chat, speak  # noqa: E402
from .commands.config_cmd import config_group  # noqa: E402
from .commands.shitpost import meme, shitpost  # noqa: E402
from .commands.transcribe import transcribe  # noqa: E402

cli.add_command(chat)
cli.add_command(speak)
cli.add_command(transcribe)
cli.add_command(shitpost)
cli.add_command(meme)
cli.add_command(config_group)
