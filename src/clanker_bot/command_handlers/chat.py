"""Chat-related command handlers."""

from __future__ import annotations

import asyncio
import logging
import uuid
from io import BytesIO

import discord

from clanker.models import Context, Message
from clanker.respond import respond
from clanker.shitposts import (
    MemeTemplate,
    ShitpostContext,
    build_request,
    load_meme_templates,
    load_templates,
    render_meme_text,
    render_shitpost,
    sample_meme_template,
    sample_template,
)

from ..views import MemePayload, ShitpostPreviewView
from ..views.shitpost_preview import RegenerateCallback
from .common import (
    build_context,
    ensure_thread,
    increment_metric,
    run_with_provider_handling,
)
from .messages import ResponseMessage
from .types import BotDependencies


async def _send_reply(
    interaction: discord.Interaction,
    reply: Message,
    audio: bytes | None = None,
) -> None:
    """Send reply to thread or channel with optional audio."""
    thread = await ensure_thread(interaction)

    if thread:
        if audio:
            file = discord.File(fp=BytesIO(audio), filename="speech.mp3")
            await thread.send(reply.content, file=file)
        else:
            await thread.send(reply.content)
        await interaction.followup.send(ResponseMessage.REPLY_IN_THREAD)
    else:
        if audio:
            file = discord.File(fp=BytesIO(audio), filename="speech.mp3")
            await interaction.followup.send(reply.content, file=file)
        else:
            await interaction.followup.send(reply.content)


async def handle_chat(
    interaction: discord.Interaction,
    prompt: str,
    deps: BotDependencies,
) -> None:
    logger = logging.getLogger(__name__)

    async def action() -> None:
        message = Message(role="user", content=prompt)
        context = build_context(interaction, deps.persona, message)
        increment_metric(deps, "chat_requests")
        reply, _audio = await respond(
            context,
            deps.llm,
            tts=None,
            replay_log_path=deps.replay_log_path,
        )
        await _send_reply(interaction, reply)

    await run_with_provider_handling(
        interaction,
        logger=logger,
        invalid_prefix=ResponseMessage.REQUEST_BLOCKED,
        error_context="chat",
        action=action,
    )


async def handle_speak(
    interaction: discord.Interaction,
    prompt: str,
    deps: BotDependencies,
) -> None:
    logger = logging.getLogger(__name__)

    async def action() -> None:
        message = Message(role="user", content=prompt)
        context = build_context(interaction, deps.persona, message)
        increment_metric(deps, "speak_requests")
        reply, audio = await respond(
            context,
            deps.llm,
            tts=deps.tts,
            replay_log_path=deps.replay_log_path,
        )
        await _send_reply(interaction, reply, audio)

    await run_with_provider_handling(
        interaction,
        logger=logger,
        invalid_prefix=ResponseMessage.REQUEST_BLOCKED,
        error_context="speak",
        action=action,
    )


async def handle_shitpost(
    interaction: discord.Interaction,
    topic: str,
    category: str | None,
    deps: BotDependencies,
) -> None:
    logger = logging.getLogger(__name__)

    async def action() -> None:
        templates = load_templates()
        template = sample_template(templates, category=category)
        increment_metric(deps, "shitpost_requests")
        context = build_context(
            interaction, deps.persona, Message(role="user", content="")
        )

        # Build shitpost context from user-provided topic
        shitpost_context = ShitpostContext(user_input=topic)

        if template.category == "meme":
            meme_templates = load_meme_templates()
            meme_template = sample_meme_template(meme_templates)

            # Track which meme template was used
            increment_metric(deps, f"meme_template_{meme_template.template_id}")

            try:
                lines = await render_meme_text(
                    context, deps.llm, meme_template, shitpost_context
                )
                increment_metric(deps, "meme_generation_success")
            except Exception:
                increment_metric(deps, "meme_generation_failure")
                raise

            caption = " | ".join(lines)
            if deps.image:
                image_payload = await deps.image.generate(
                    {"template": meme_template.template_id, "text": lines}
                )
                if isinstance(image_payload, str):
                    image_bytes = image_payload.encode()
                else:
                    image_bytes = image_payload
                file = discord.File(fp=BytesIO(image_bytes), filename="meme.png")
                await interaction.followup.send(caption, file=file)
            else:
                await interaction.followup.send(caption)
        else:
            request = build_request(template, shitpost_context)
            reply = await render_shitpost(context, deps.llm, request)
            await interaction.followup.send(reply.content)

    await run_with_provider_handling(
        interaction,
        logger=logger,
        invalid_prefix=ResponseMessage.INVALID_CATEGORY,
        error_context="shitpost",
        action=action,
    )


# Default context settings (not exposed to users yet)
_DEFAULT_CONTEXT_MESSAGES = 10


async def _fetch_channel_messages(
    channel: discord.abc.Messageable,
    limit: int = _DEFAULT_CONTEXT_MESSAGES,
) -> list[dict[str, str]]:
    """Fetch recent messages from a channel for context."""
    messages: list[dict[str, str]] = []
    async for msg in channel.history(limit=limit):
        if msg.author.bot:
            continue
        if not msg.content.strip():
            continue
        messages.append(
            {
                "role": "user",
                "content": f"{msg.author.display_name}: {msg.content}",
            }
        )
    messages.reverse()  # Oldest first
    return messages


def _get_voice_context(
    guild_id: int | None,
    deps: BotDependencies,
    logger: logging.Logger,
) -> tuple[tuple | None, str]:
    """Get voice transcript context if available.

    Returns:
        Tuple of (transcript_utterances, channel_type)
    """
    if not guild_id or not deps.transcript_buffer:
        return None, "text"

    events = deps.transcript_buffer.get(guild_id)
    if not events:
        return None, "text"

    logger.info(
        "shitpost.using_voice_context",
        extra={"guild_id": guild_id, "event_count": len(events)},
    )
    return tuple(events), "voice"


async def _build_shitpost_context(
    interaction: discord.Interaction,
    guidance: str | None,
    deps: BotDependencies,
    logger: logging.Logger,
) -> ShitpostContext:
    """Build ShitpostContext from voice transcript or channel history."""
    transcript_utterances, channel_type = _get_voice_context(
        interaction.guild_id, deps, logger
    )

    messages: list[dict[str, str]] = []
    if not transcript_utterances:
        channel = interaction.channel
        if channel is not None and hasattr(channel, "history"):
            messages = await _fetch_channel_messages(channel)  # type: ignore[arg-type]

    return ShitpostContext(
        user_input=guidance,
        messages=tuple(messages) if messages else None,
        transcript_utterances=transcript_utterances,
        channel_type=channel_type,
    )


async def _generate_single_meme(
    deps: BotDependencies,
    shitpost_context: ShitpostContext,
    meme_template: MemeTemplate,
) -> tuple[MemePayload, discord.Embed]:
    """Generate a single meme and return payload + embed."""
    context = Context(
        request_id=str(uuid.uuid4()),
        user_id=0,
        guild_id=None,
        channel_id=0,
        persona=deps.persona,
        messages=[Message(role="user", content="")],
        metadata={"source": "discord"},
    )

    lines = await render_meme_text(context, deps.llm, meme_template, shitpost_context)
    caption = " | ".join(lines)

    image_bytes: bytes | None = None
    if deps.image:
        image_payload = await deps.image.generate(
            {"template": meme_template.template_id, "text": lines}
        )
        if isinstance(image_payload, str):
            image_bytes = image_payload.encode()
        else:
            image_bytes = image_payload

    payload = MemePayload(
        text=caption,
        image_bytes=image_bytes,
        template_id=meme_template.template_id,
    )

    embed = discord.Embed(
        title=f"Meme Preview: {meme_template.template_id}",
        description=caption,
        color=discord.Color.blue(),
    )
    if meme_template.variant_description:
        embed.set_footer(text=meme_template.variant_description)

    return payload, embed


async def _generate_memes_parallel(
    n: int,
    deps: BotDependencies,
    shitpost_context: ShitpostContext,
    meme_templates: tuple[MemeTemplate, ...],
) -> list[tuple[MemePayload, discord.Embed, MemeTemplate]]:
    """Generate n memes in parallel with random templates."""

    async def generate_one() -> tuple[MemePayload, discord.Embed, MemeTemplate]:
        template = sample_meme_template(meme_templates)
        payload, embed = await _generate_single_meme(deps, shitpost_context, template)
        return payload, embed, template

    return list(await asyncio.gather(*[generate_one() for _ in range(n)]))


def _create_regenerate_callback(
    deps: BotDependencies,
    shitpost_context: ShitpostContext,
    meme_templates: tuple[MemeTemplate, ...],
) -> RegenerateCallback:
    """Create a regenerate callback that picks a new random template."""

    async def regenerate() -> tuple[MemePayload, discord.Embed]:
        new_template = sample_meme_template(meme_templates)
        return await _generate_single_meme(deps, shitpost_context, new_template)

    return regenerate


async def _send_preview(
    interaction: discord.Interaction,
    payload: MemePayload,
    embed: discord.Embed,
    view: ShitpostPreviewView,
) -> None:
    """Send a single preview as ephemeral followup."""
    if payload.image_bytes:
        file = discord.File(fp=BytesIO(payload.image_bytes), filename="meme.png")
        embed.set_image(url="attachment://meme.png")
        await interaction.followup.send(
            embed=embed, file=file, view=view, ephemeral=True
        )
    else:
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def handle_shitpost_preview(
    interaction: discord.Interaction,
    n: int,
    guidance: str | None,
    deps: BotDependencies,
) -> None:
    """Handle shitpost command with ephemeral preview workflow."""
    logger = logging.getLogger(__name__)
    n = max(1, min(n, 5))

    async def action() -> None:
        increment_metric(deps, "shitpost_preview_requests")

        shitpost_context = await _build_shitpost_context(
            interaction, guidance, deps, logger
        )
        meme_templates = load_meme_templates()
        results = await _generate_memes_parallel(
            n, deps, shitpost_context, meme_templates
        )

        for i, (payload, embed, template) in enumerate(results, 1):
            preview_id = str(uuid.uuid4())
            view = ShitpostPreviewView(
                invoker_id=interaction.user.id,
                preview_id=preview_id,
                payload=payload,
                embed=embed,
                regenerate_callback=_create_regenerate_callback(
                    deps, shitpost_context, meme_templates
                ),
            )

            await _send_preview(interaction, payload, embed, view)
            increment_metric(deps, f"meme_template_{template.template_id}")
            logger.info(
                "shitpost.preview_sent",
                extra={
                    "preview_id": preview_id,
                    "preview_index": i,
                    "template_id": template.template_id,
                    "user_id": interaction.user.id,
                },
            )

    await run_with_provider_handling(
        interaction,
        logger=logger,
        invalid_prefix=ResponseMessage.INVALID_CATEGORY,
        error_context="shitpost_preview",
        action=action,
        ephemeral=True,
    )
