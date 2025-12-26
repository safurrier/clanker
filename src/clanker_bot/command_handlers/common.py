"""Common helpers for command handlers."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import discord
from loguru import logger

from clanker.models import Context, Message, Persona
from clanker.providers.errors import PermanentProviderError, TransientProviderError

from .messages import ResponseMessage
from .types import BotDependencies


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
        return await channel.create_thread(  # type: ignore[union-attr, call-arg]
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
