"""Handler for /transcript command."""

from __future__ import annotations

import discord
from loguru import logger

from .types import BotDependencies


def _format_transcript(events: list) -> str:
    """Format transcript events into a readable string."""
    if not events:
        return ""

    lines = ["**Recent Voice Transcript**\n"]
    for event in events:
        time_str = event.start_time.strftime("%H:%M:%S")
        lines.append(f"`{time_str}` <@{event.speaker_id}>: {event.text}")

    return "\n".join(lines)


async def handle_transcript(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    """Display recent voice transcripts for debugging.

    Shows the same transcript data used by /shitpost for context.
    Response is ephemeral (only visible to the invoker).
    """
    await interaction.response.defer(ephemeral=True)

    guild_id = interaction.guild_id
    user_id = interaction.user.id if interaction.user else None
    logger.debug(
        "transcript.requested: user={}, guild={}",
        user_id,
        guild_id,
    )

    if not guild_id:
        logger.debug("transcript.rejected: no guild_id")
        await interaction.followup.send(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    # Get transcript buffer
    if not deps.transcript_buffer:
        logger.debug(
            "transcript.no_buffer: guild={}, buffer_available={}",
            guild_id,
            deps.transcript_buffer is not None,
        )
        await interaction.followup.send(
            "No recent transcripts available. Use `/join` to start capturing voice.",
            ephemeral=True,
        )
        return

    events = deps.transcript_buffer.get(guild_id)
    logger.debug(
        "transcript.events_retrieved: guild={}, count={}",
        guild_id,
        len(events),
    )
    if not events:
        await interaction.followup.send(
            "No recent transcripts available. Use `/join` to start capturing voice.",
            ephemeral=True,
        )
        return

    # Format and send
    formatted = _format_transcript(events)
    if len(formatted) > 2000:
        # Discord message limit - truncate
        formatted = formatted[:1997] + "..."

    await interaction.followup.send(formatted, ephemeral=True)
    logger.info(
        "transcript.displayed",
        guild_id=guild_id,
        event_count=len(events),
    )
