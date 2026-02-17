"""Config subcommands."""

from __future__ import annotations

from pathlib import Path

import click
import yaml

from clanker.config import load_config
from clanker_cli.main import CliContext
from clanker_cli.output import output_text


@click.group("config")
def config_group() -> None:
    """Inspect and validate configuration."""


@config_group.command()
@click.pass_obj
def show(ctx: CliContext) -> None:
    """Dump the resolved configuration."""
    if ctx.config is None:
        raise click.ClickException(
            "No config loaded. Use --config or set CLANKER_CONFIG_PATH."
        )
    data = {
        "providers": {
            "llm": ctx.config.provider_config.llm,
            "stt": ctx.config.provider_config.stt,
            "tts": ctx.config.provider_config.tts,
            "image": ctx.config.provider_config.image,
        },
        "default_persona": ctx.config.default_persona_id,
        "personas": [
            {
                "id": p.id,
                "display_name": p.display_name,
                "system_prompt": p.system_prompt,
                "tts_voice": p.tts_voice,
            }
            for p in ctx.config.personas
        ],
    }
    output_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


@config_group.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def validate(path: Path) -> None:
    """Validate a config YAML and check provider env vars."""
    try:
        config = load_config(path)
    except (ValueError, yaml.YAMLError) as exc:
        raise click.ClickException(f"Invalid config: {exc}") from exc

    from clanker.providers.factory import ProviderFactory

    factory = ProviderFactory()
    try:
        factory.validate(config.provider_config)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    output_text("Config is valid.")


@config_group.command()
@click.pass_obj
def personas(ctx: CliContext) -> None:
    """List available personas."""
    if ctx.config is None:
        raise click.ClickException(
            "No config loaded. Use --config or set CLANKER_CONFIG_PATH."
        )
    for p in ctx.config.personas:
        parts = [p.id, p.display_name]
        if p.tts_voice:
            parts.append(f"voice={p.tts_voice}")
        output_text("  ".join(parts))
