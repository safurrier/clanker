"""Common helpers for command handlers."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Protocol, cast

import discord

from clanker.models import Context, Message, Persona
from clanker.providers.errors import PermanentProviderError, TransientProviderError

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


class ThreadCreator(Protocol):
    async def create_thread(self, name: str, **kwargs: object) -> discord.Thread: ...


async def ensure_thread(interaction: discord.Interaction) -> discord.Thread | None:
    channel = interaction.channel
    if channel and hasattr(channel, "create_thread"):
        creator = cast(ThreadCreator, channel)
        return await creator.create_thread(
            name=f"clanker-{uuid.uuid4().hex[:6]}",
            type=discord.ChannelType.public_thread,
        )
    return None


async def run_with_provider_handling(
    interaction: discord.Interaction,
    *,
    logger: logging.Logger,
    invalid_prefix: str,
    error_context: str,
    action: Callable[[], Awaitable[None]],
) -> None:
    await interaction.response.defer()
    try:
        await action()
    except ValueError as exc:
        await interaction.followup.send(f"{invalid_prefix}: {exc}", ephemeral=True)
    except TransientProviderError:
        await interaction.followup.send(
            "⏳ Service temporarily unavailable. Please try again.", ephemeral=True
        )
    except PermanentProviderError as exc:
        await interaction.followup.send(
            "❌ Configuration error. Please contact an admin.", ephemeral=True
        )
        logger.error(
            "Provider error in %s",
            error_context,
            exc_info=True,
            extra={"error": str(exc)},
        )
    except Exception as exc:
        await interaction.followup.send(
            "❌ An unexpected error occurred.", ephemeral=True
        )
        logger.error(
            "Unexpected error in %s",
            error_context,
            exc_info=True,
            extra={"error": str(exc)},
        )
