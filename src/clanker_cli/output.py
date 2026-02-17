"""Output helpers for the CLI."""

from __future__ import annotations

import json
from pathlib import Path

import click


def output_text(text: str) -> None:
    """Print plain text to stdout."""
    click.echo(text)


def output_json(data: object) -> None:
    """Print JSON-formatted data to stdout."""
    click.echo(json.dumps(data, indent=2, ensure_ascii=False))


def write_audio(audio_bytes: bytes, path: Path) -> None:
    """Write audio bytes to a file."""
    path.write_bytes(audio_bytes)
    click.echo(f"Audio written to {path}")
