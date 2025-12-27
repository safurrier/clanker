"""Common helpers for command handlers."""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from typing import cast

import discord
from loguru import logger

from clanker.models import Context, Message, Persona
from clanker.providers.errors import PermanentProviderError, TransientProviderError

from .messages import ResponseMessage
from .types import BotDependencies

# Pattern for clanker-created threads: clanker-{6 lowercase hex chars}
CLANKER_THREAD_PATTERN = re.compile(r"^clanker-[a-f0-9]{6}$")

# Discord message character limit
DISCORD_MESSAGE_LIMIT = 2000


def chunk_message(text: str, max_length: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    """Split a message into chunks that fit within Discord's character limit.

    Attempts to split at natural boundaries in this order of preference:
    1. Newlines (splits after newline, preserving it in the first chunk)
    2. Spaces (splits after space, preserving it in the first chunk)
    3. Hard cut (when no boundaries found)

    Args:
        text: The message text to chunk
        max_length: Maximum characters per chunk (default: 2000)

    Returns:
        List of message chunks, each under max_length characters.
        Returns empty list for empty/whitespace-only input.
    """
    if not text or not text.strip():
        return []

    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to find a natural break point within the limit
        chunk = remaining[:max_length]

        # Preference 1: Split at last newline (keep newline in first chunk)
        newline_pos = chunk.rfind("\n")
        if newline_pos > 0:
            # Include the newline in the first chunk
            chunks.append(remaining[: newline_pos + 1])
            remaining = remaining[newline_pos + 1 :]
            continue

        # Preference 2: Split at last space (keep space in first chunk)
        space_pos = chunk.rfind(" ")
        if space_pos > 0:
            # Include the space in the first chunk
            chunks.append(remaining[: space_pos + 1])
            remaining = remaining[space_pos + 1 :]
            continue

        # Preference 3: Hard split (no natural boundary)
        chunks.append(chunk)
        remaining = remaining[max_length:]

    return chunks


def is_clanker_thread(
    channel: discord.abc.GuildChannel
    | discord.Thread
    | discord.abc.PrivateChannel
    | discord.PartialMessageable
    | None,
) -> bool:
    """Check if this is a thread created by the bot.

    Returns True if channel is a discord.Thread with a name matching
    the clanker-{6 hex chars} pattern.
    """
    if not isinstance(channel, discord.Thread):
        return False
    return bool(CLANKER_THREAD_PATTERN.match(channel.name))


def build_context(
    interaction: discord.Interaction,
    persona: Persona,
    message: Message,
) -> Context:
    """Build a Context from a Discord interaction and prompt."""
    return Context(
        request_id=str(uuid.uuid4()),
        user_id=interaction.user.id,
        guild_id=interaction.guild_id,
        channel_id=interaction.channel_id or 0,
        persona=persona,
        messages=[message],
        metadata={"source": "discord"},
    )


def increment_metric(deps: BotDependencies, key: str) -> None:
    if deps.metrics:
        deps.metrics.increment(key)


async def ensure_thread(interaction: discord.Interaction) -> discord.Thread | None:
    """Create a thread for the interaction if the channel supports it."""
    channel = interaction.channel
    # Check specific channel types that support threads
    # Note: Using isinstance for production code, but also support duck-typing for tests
    if isinstance(channel, discord.TextChannel | discord.ForumChannel) or (
        hasattr(channel, "create_thread")
        and not isinstance(channel, discord.VoiceChannel | discord.StageChannel)
    ):
        # Cast is safe: we've verified channel has create_thread and isn't Voice/Stage
        text_channel = cast(discord.TextChannel, channel)
        return await text_channel.create_thread(
            name=f"clanker-{uuid.uuid4().hex[:6]}",
            type=discord.ChannelType.public_thread,
        )
    return None


async def run_with_provider_handling(
    interaction: discord.Interaction,
    *,
    invalid_prefix: str,
    error_context: str,
    action: Callable[[], Awaitable[None]],
    ephemeral: bool = False,
) -> None:
    await interaction.response.defer(ephemeral=ephemeral)
    try:
        await action()
    except ValueError as exc:
        await interaction.followup.send(f"{invalid_prefix}: {exc}", ephemeral=True)
    except TransientProviderError:
        await interaction.followup.send(
            ResponseMessage.SERVICE_UNAVAILABLE, ephemeral=True
        )
    except PermanentProviderError as exc:
        await interaction.followup.send(ResponseMessage.CONFIG_ERROR, ephemeral=True)
        logger.opt(exception=True).error(
            "Provider error in {context}: {error}",
            context=error_context,
            error=str(exc),
        )
    except Exception as exc:
        await interaction.followup.send(
            ResponseMessage.UNEXPECTED_ERROR, ephemeral=True
        )
        logger.opt(exception=True).error(
            "Unexpected error in {context}: {error}",
            context=error_context,
            error=str(exc),
        )
