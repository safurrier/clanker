"""Handler for automatic thread replies."""

from __future__ import annotations

import uuid
from typing import cast

import discord
from loguru import logger

from clanker.models import Context, Message
from clanker.respond import respond

from .common import chunk_message, increment_metric
from .types import BotDependencies


async def _fetch_thread_history(
    thread: discord.Thread,
    limit: int = 20,
) -> list[Message]:
    """Fetch thread history as Message objects.

    Returns messages in chronological order (oldest first).
    Properly labels bot messages as 'assistant' role.
    """
    messages: list[Message] = []
    bot_id = thread.guild.me.id if thread.guild and thread.guild.me else None

    async for msg in thread.history(limit=limit):
        if not msg.content.strip():
            continue

        # Determine role based on author
        if msg.author.bot and bot_id and msg.author.id == bot_id:
            role = "assistant"
            content = msg.content
        else:
            role = "user"
            # Include username for multi-user context
            content = f"{msg.author.display_name}: {msg.content}"

        messages.append(Message(role=role, content=content))

    messages.reverse()  # Discord returns newest-first, we want oldest-first
    return messages


async def handle_thread_message(
    message: discord.Message,
    deps: BotDependencies,
) -> None:
    """Handle a regular message in a clanker thread.

    This is called from on_message when a user posts in a thread
    that the bot created.
    """
    channel = message.channel
    # Check for discord.Thread or duck-typed equivalent (for testing)
    if not isinstance(channel, discord.Thread) and not hasattr(channel, "history"):
        return

    # Type narrowing: we know channel is a Thread at this point
    thread = cast(discord.Thread, channel)

    try:
        # Show typing indicator while processing
        async with thread.typing():
            # Fetch full thread history
            history = await _fetch_thread_history(thread, limit=20)

            # Build context
            context = Context(
                request_id=str(uuid.uuid4()),
                user_id=message.author.id,
                guild_id=message.guild.id if message.guild else None,
                channel_id=thread.id,
                persona=deps.persona,
                messages=history,
                metadata={"source": "discord", "trigger": "thread_message"},
            )

            increment_metric(deps, "thread_chat_requests")

            # Generate response
            replay_log_path = getattr(deps, "replay_log_path", None)
            reply, _audio = await respond(
                context,
                deps.llm,
                tts=None,
                replay_log_path=replay_log_path,
            )

            # Send reply (split into chunks if over Discord limit)
            for chunk in chunk_message(reply.content):
                await thread.send(chunk)

            logger.info(
                "thread_chat.replied",
                thread_id=thread.id,
                user_id=message.author.id,
                message_count=len(history),
            )

    except Exception as e:
        logger.opt(exception=True).error(
            "thread_chat.error",
            thread_id=thread.id,
            error=str(e),
        )
        # Send error message to thread
        await thread.send("Sorry, I encountered an error processing that message.")
