"""Chat-related command handlers."""

from __future__ import annotations

import logging
from io import BytesIO

import discord

from clanker.models import Message
from clanker.respond import respond
from clanker.shitposts import (
    build_request,
    load_templates,
    render_shitpost,
    sample_template,
)

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
        request = build_request(template, topic)
        increment_metric(deps, "shitpost_requests")
        reply = await render_shitpost(
            build_context(interaction, deps.persona, Message(role="user", content="")),
            deps.llm,
            request,
        )
        if deps.image and template.category == "meme":
            image_payload = await deps.image.generate(
                {"template": template.name, "text": reply.content}
            )
            if isinstance(image_payload, str):
                image_bytes = image_payload.encode()
            else:
                image_bytes = image_payload
            file = discord.File(fp=BytesIO(image_bytes), filename="meme.png")
            await interaction.followup.send(reply.content, file=file)
        else:
            await interaction.followup.send(reply.content)

    await run_with_provider_handling(
        interaction,
        logger=logger,
        invalid_prefix=ResponseMessage.INVALID_CATEGORY,
        error_context="shitpost",
        action=action,
    )
