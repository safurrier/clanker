"""Chat-related command handlers."""

from __future__ import annotations

import asyncio
import uuid
from io import BytesIO

import discord
from loguru import logger

from clanker.models import Context, Message
from clanker.respond import respond
from clanker.shitposts import (
    MemeTemplate,
    ShitpostContext,
    load_meme_templates,
    render_meme_text,
    sample_meme_template,
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
        invalid_prefix=ResponseMessage.REQUEST_BLOCKED,
        error_context="chat",
        action=action,
    )


async def handle_speak(
    interaction: discord.Interaction,
    prompt: str,
    deps: BotDependencies,
) -> None:
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
        invalid_prefix=ResponseMessage.REQUEST_BLOCKED,
        error_context="speak",
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
        guild_id=guild_id,
        event_count=len(events),
    )
    return tuple(events), "voice"


async def _build_shitpost_context(
    interaction: discord.Interaction,
    guidance: str | None,
    deps: BotDependencies,
) -> ShitpostContext:
    """Build ShitpostContext from voice transcript or channel history."""
    transcript_utterances, channel_type = _get_voice_context(interaction.guild_id, deps)

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
    *,
    user_id: int,
    guild_id: int | None,
    channel_id: int,
) -> tuple[MemePayload, discord.Embed]:
    """Generate a single meme and return payload + embed."""
    context = Context(
        request_id=str(uuid.uuid4()),
        user_id=user_id,
        guild_id=guild_id,
        channel_id=channel_id,
        persona=deps.persona,
        messages=[Message(role="user", content="")],
        metadata={"source": "discord"},
    )

    lines = await render_meme_text(context, deps.llm, meme_template, shitpost_context)
    caption = " | ".join(lines)

    image_bytes: bytes | None = None
    if deps.image:
        logger.info(
            "meme.generating_image: template={}, lines={}",
            meme_template.template_id,
            lines,
            template_id=meme_template.template_id,
            text_lines=lines,
        )
        image_payload = await deps.image.generate(
            {"template": meme_template.template_id, "text": lines}
        )
        if isinstance(image_payload, str):
            image_bytes = image_payload.encode()
        else:
            image_bytes = image_payload
        image_size = len(image_bytes) if image_bytes else 0
        logger.info(
            "meme.image_generated: template={}, size={}",
            meme_template.template_id,
            image_size,
            template_id=meme_template.template_id,
            image_size=image_size,
        )
    else:
        logger.warning(
            "meme.no_image_provider: template={} (hint: set image provider to 'memegen')",
            meme_template.template_id,
            template_id=meme_template.template_id,
        )

    payload = MemePayload(
        text=caption,
        image_bytes=image_bytes,
        template_id=meme_template.template_id,
    )

    embed = discord.Embed(
        title="Generated Shitpost",
        color=discord.Color.blue(),
    )

    return payload, embed


async def _generate_memes_parallel(
    n: int,
    deps: BotDependencies,
    shitpost_context: ShitpostContext,
    meme_templates: tuple[MemeTemplate, ...],
    *,
    user_id: int,
    guild_id: int | None,
    channel_id: int,
) -> list[tuple[MemePayload, discord.Embed, MemeTemplate]]:
    """Generate n memes in parallel with random templates."""

    async def generate_one() -> tuple[MemePayload, discord.Embed, MemeTemplate]:
        template = sample_meme_template(meme_templates)
        payload, embed = await _generate_single_meme(
            deps,
            shitpost_context,
            template,
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
        )
        return payload, embed, template

    return list(await asyncio.gather(*[generate_one() for _ in range(n)]))


def _create_regenerate_callback(
    deps: BotDependencies,
    shitpost_context: ShitpostContext,
    meme_templates: tuple[MemeTemplate, ...],
    *,
    user_id: int,
    guild_id: int | None,
    channel_id: int,
) -> RegenerateCallback:
    """Create a regenerate callback that picks a new random template."""

    async def regenerate() -> tuple[MemePayload, discord.Embed]:
        new_template = sample_meme_template(meme_templates)
        return await _generate_single_meme(
            deps,
            shitpost_context,
            new_template,
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
        )

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
    n = max(1, min(n, 5))

    async def action() -> None:
        increment_metric(deps, "shitpost_preview_requests")

        # Extract request metadata for Context objects
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        channel_id = interaction.channel_id or 0

        shitpost_context = await _build_shitpost_context(interaction, guidance, deps)
        meme_templates = load_meme_templates()
        results = await _generate_memes_parallel(
            n,
            deps,
            shitpost_context,
            meme_templates,
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
        )

        for i, (payload, embed, template) in enumerate(results, 1):
            preview_id = str(uuid.uuid4())
            view = ShitpostPreviewView(
                invoker_id=user_id,
                preview_id=preview_id,
                payload=payload,
                embed=embed,
                regenerate_callback=_create_regenerate_callback(
                    deps,
                    shitpost_context,
                    meme_templates,
                    user_id=user_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                ),
            )

            await _send_preview(interaction, payload, embed, view)
            increment_metric(deps, f"meme_template_{template.template_id}")
            logger.info(
                "shitpost.preview_sent",
                preview_id=preview_id,
                preview_index=i,
                template_id=template.template_id,
                user_id=interaction.user.id,
            )

    await run_with_provider_handling(
        interaction,
        invalid_prefix=ResponseMessage.INVALID_CATEGORY,
        error_context="shitpost_preview",
        action=action,
        ephemeral=True,
    )
