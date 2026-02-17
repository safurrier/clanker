"""Shitpost and meme commands."""

from __future__ import annotations

from urllib.parse import quote

import click

from clanker.providers.errors import PermanentProviderError, TransientProviderError
from clanker.shitposts import (
    ShitpostContext,
    build_request,
    load_meme_templates,
    load_templates,
    render_meme_text,
    render_shitpost,
    sample_meme_template,
    sample_template,
)
from clanker_cli.main import CliContext, build_cli_context, run_async
from clanker_cli.output import output_json, output_text


@click.command()
@click.argument("topic", required=False)
@click.option("--template", "template_name", default=None, help="Template name.")
@click.option("--category", default=None, help="Template category.")
@click.option(
    "--list-templates", is_flag=True, help="List available templates and exit."
)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON.")
@click.pass_obj
def shitpost(
    ctx: CliContext,
    topic: str | None,
    template_name: str | None,
    category: str | None,
    list_templates: bool,
    use_json: bool,
) -> None:
    """Generate a shitpost."""
    if list_templates:
        templates = load_templates()
        if use_json:
            output_json(
                [
                    {"name": t.name, "category": t.category, "tags": list(t.tags)}
                    for t in templates
                ]
            )
        else:
            for t in templates:
                output_text(f"{t.name}  [{t.category}]")
        return
    run_async(_shitpost(ctx, topic, template_name, category, use_json))


async def _shitpost(
    ctx: CliContext,
    topic: str | None,
    template_name: str | None,
    category: str | None,
    use_json: bool,
) -> None:
    templates = load_templates()
    try:
        template = sample_template(templates, category=category, name=template_name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    shitpost_ctx = ShitpostContext(user_input=topic)
    request = build_request(template, shitpost_ctx)
    context = build_cli_context(ctx.persona, topic or "shitpost")

    llm_name = ctx.config.provider_config.llm if ctx.config else "openai"
    try:
        llm = ctx.factory.get_llm(llm_name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        result = await render_shitpost(context, llm, request)
    except (TransientProviderError, PermanentProviderError) as exc:
        raise click.ClickException(str(exc)) from exc

    if use_json:
        output_json(
            {
                "template": template.name,
                "category": template.category,
                "content": result.content,
            }
        )
    else:
        output_text(result.content)


@click.command()
@click.argument("topic", required=False)
@click.option("--template", "template_id", default=None, help="Meme template ID.")
@click.option(
    "--list-templates", is_flag=True, help="List available meme templates and exit."
)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON.")
@click.pass_obj
def meme(
    ctx: CliContext,
    topic: str | None,
    template_id: str | None,
    list_templates: bool,
    use_json: bool,
) -> None:
    """Generate meme text and a memegen URL."""
    if list_templates:
        templates = load_meme_templates()
        if use_json:
            output_json(
                [
                    {
                        "template_id": t.template_id,
                        "variant": t.variant,
                        "text_slots": t.text_slots,
                    }
                    for t in templates
                ]
            )
        else:
            for t in templates:
                output_text(f"{t.template_id}  {t.variant}  (slots: {t.text_slots})")
        return
    run_async(_meme(ctx, topic, template_id, use_json))


async def _meme(
    ctx: CliContext,
    topic: str | None,
    template_id: str | None,
    use_json: bool,
) -> None:
    templates = load_meme_templates()
    try:
        template = sample_meme_template(templates, template_id=template_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    shitpost_ctx = ShitpostContext(user_input=topic)
    context = build_cli_context(ctx.persona, topic or "meme")

    llm_name = ctx.config.provider_config.llm if ctx.config else "openai"
    try:
        llm = ctx.factory.get_llm(llm_name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        lines = await render_meme_text(context, llm, template, shitpost_ctx)
    except (TransientProviderError, PermanentProviderError) as exc:
        raise click.ClickException(str(exc)) from exc

    encoded = "/".join(quote(line, safe="") for line in lines)
    url = f"https://api.memegen.link/images/{template.template_id}/{encoded}.png"

    if use_json:
        output_json(
            {
                "template_id": template.template_id,
                "variant": template.variant,
                "lines": lines,
                "url": url,
            }
        )
    else:
        for line in lines:
            output_text(line)
        output_text(url)
