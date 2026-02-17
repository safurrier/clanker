"""Chat and speak commands."""

from __future__ import annotations

from pathlib import Path

import click

from clanker.providers.errors import PermanentProviderError, TransientProviderError
from clanker.respond import respond
from clanker_cli.main import CliContext, build_cli_context, read_prompt, run_async
from clanker_cli.output import output_json, output_text, write_audio


@click.command()
@click.argument("prompt", required=False)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON.")
@click.pass_obj
def chat(ctx: CliContext, prompt: str | None, use_json: bool) -> None:
    """Send a prompt to the LLM and print the response."""
    run_async(_chat(ctx, prompt, use_json))


async def _chat(ctx: CliContext, prompt: str | None, use_json: bool) -> None:
    text = read_prompt(prompt)
    context = build_cli_context(ctx.persona, text)
    provider_name = _llm_provider_name(ctx)
    try:
        llm = ctx.factory.get_llm(provider_name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        reply, _ = await respond(context, llm)
    except (TransientProviderError, PermanentProviderError) as exc:
        raise click.ClickException(str(exc)) from exc

    if use_json:
        output_json({"role": reply.role, "content": reply.content})
    else:
        output_text(reply.content)


@click.command()
@click.argument("prompt", required=False)
@click.option(
    "--output",
    "-o",
    "output_path",
    type=click.Path(),
    default="response.mp3",
    show_default=True,
    help="Audio output file path.",
)
@click.option("--voice", default=None, help="Override TTS voice ID.")
@click.pass_obj
def speak(
    ctx: CliContext,
    prompt: str | None,
    output_path: str,
    voice: str | None,
) -> None:
    """Send a prompt to the LLM and synthesize speech."""
    run_async(_speak(ctx, prompt, output_path, voice))


async def _speak(
    ctx: CliContext,
    prompt: str | None,
    output_path: str,
    voice: str | None,
) -> None:
    text = read_prompt(prompt)

    # If a voice override is provided, swap it into the persona
    persona = ctx.persona
    if voice:
        from clanker.models import Persona

        persona = Persona(
            id=persona.id,
            display_name=persona.display_name,
            system_prompt=persona.system_prompt,
            tts_voice=voice,
            providers=persona.providers,
        )
    elif not persona.tts_voice:
        raise click.ClickException(
            "No TTS voice configured. Use --voice or set tts_voice in config."
        )

    context = build_cli_context(persona, text)
    llm_name = _llm_provider_name(ctx)
    tts_name = _tts_provider_name(ctx)
    try:
        llm = ctx.factory.get_llm(llm_name)
        tts = ctx.factory.get_tts(tts_name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        reply, audio = await respond(context, llm, tts=tts)
    except (TransientProviderError, PermanentProviderError) as exc:
        raise click.ClickException(str(exc)) from exc

    output_text(reply.content)
    if audio:
        write_audio(audio, Path(output_path))
    else:
        click.echo("Warning: no audio generated.", err=True)


def _llm_provider_name(ctx: CliContext) -> str:
    if ctx.config:
        return ctx.config.provider_config.llm
    return "openai"


def _tts_provider_name(ctx: CliContext) -> str:
    if ctx.config:
        return ctx.config.provider_config.tts
    return "elevenlabs"
