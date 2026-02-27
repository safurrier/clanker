"""Config subcommands."""

from __future__ import annotations

from pathlib import Path

import click
import yaml

from clanker.config import load_config
from clanker_cli.main import CliContext
from clanker_cli.output import output_text


@click.group(
    "config",
    epilog="""\b
Examples:
  clanker --config config.yaml config show
  clanker config validate config.yaml
  clanker --config config.yaml config personas
""",
)
def config_group() -> None:
    """Inspect and validate Clanker configuration files.

    Requires --config or the CLANKER_CONFIG_PATH env var for
    the 'show' and 'personas' subcommands.
    """


@config_group.command()
@click.pass_obj
def show(ctx: CliContext) -> None:
    """Print the resolved configuration as YAML.

    Shows provider mappings, default persona, and all persona
    definitions after config loading and merging.
    """
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
    """Validate a config file and check that required env vars are set.

    Parses the YAML, validates its structure, then checks that each
    configured provider's API key is available in the environment.
    """
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
    """List all personas defined in the config.

    Prints each persona's ID, display name, and TTS voice (if set).
    """
    if ctx.config is None:
        raise click.ClickException(
            "No config loaded. Use --config or set CLANKER_CONFIG_PATH."
        )
    for p in ctx.config.personas:
        parts = [p.id, p.display_name]
        if p.tts_voice:
            parts.append(f"voice={p.tts_voice}")
        output_text("  ".join(parts))
