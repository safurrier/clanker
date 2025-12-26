"""Voice-related command handlers."""

from __future__ import annotations

from typing import cast

import discord
import discord.ext.voice_recv as voice_recv
from loguru import logger

from ..voice_ingest import start_voice_ingest, voice_client_cls
from .messages import ResponseMessage
from .types import BotDependencies


def _can_join_meeting(interaction: discord.Interaction, deps: BotDependencies) -> bool:
    """Check if new meetings are allowed."""
    return not deps.admin_state or deps.admin_state.allow_new_meetings


def _get_user_voice_channel(
    interaction: discord.Interaction,
) -> discord.VoiceChannel | None:
    """Get the voice channel the user is currently in."""
    if not interaction.user:
        return None
    voice_state = getattr(interaction.user, "voice", None)
    return getattr(voice_state, "channel", None) if voice_state else None


def _get_voice_client_cls(
    deps: BotDependencies,
) -> type[discord.VoiceClient] | None:
    """Get the voice client class if voice ingest is enabled."""
    return voice_client_cls() if deps.voice_ingest_enabled else None


async def _setup_transcription(
    deps: BotDependencies,
    voice_client_cls: type[discord.VoiceClient] | None,
) -> str:
    """Set up transcription and return status message."""
    if not deps.voice_ingest_enabled:
        return ResponseMessage.JOINED_VOICE

    if deps.stt is None:
        return f"{ResponseMessage.JOINED_VOICE} ({ResponseMessage.TRANSCRIPTION_UNAVAILABLE_NO_STT})"

    if voice_client_cls is None:
        return f"{ResponseMessage.JOINED_VOICE} ({ResponseMessage.TRANSCRIPTION_UNAVAILABLE_BUILD})"

    try:
        voice_client = deps.voice_manager.voice_client
        if voice_client is None:
            raise RuntimeError("Voice client not available.")
        # Safe cast: we just joined with voice_recv.VoiceRecvClient class
        recv_client = cast(voice_recv.VoiceRecvClient, voice_client)
        await start_voice_ingest(recv_client, deps.stt)
        return (
            f"{ResponseMessage.JOINED_VOICE} ({ResponseMessage.TRANSCRIPTION_ENABLED})"
        )
    except Exception:
        logger.exception("Failed to start voice ingest.")
        return f"{ResponseMessage.JOINED_VOICE} ({ResponseMessage.TRANSCRIPTION_SETUP_ERROR})"


async def handle_join(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    # Validate preconditions
    if not _can_join_meeting(interaction, deps):
        await interaction.response.send_message(ResponseMessage.NEW_MEETINGS_DISABLED)
        return

    if not interaction.user:
        await interaction.response.send_message(ResponseMessage.UNABLE_TO_RESOLVE_VOICE)
        return

    voice_channel = _get_user_voice_channel(interaction)
    if not voice_channel:
        await interaction.response.send_message(ResponseMessage.JOIN_VOICE_FIRST)
        return

    # Join the voice channel
    voice_client_cls = _get_voice_client_cls(deps)
    ok, status = await deps.voice_manager.join(
        voice_channel, voice_client_cls=voice_client_cls
    )

    if not ok:
        await interaction.response.send_message(status)
        return

    # Setup transcription and send response
    message = await _setup_transcription(deps, voice_client_cls)
    await interaction.response.send_message(message)


async def handle_leave(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    ok, status = await deps.voice_manager.leave()
    if ok:
        await interaction.response.send_message(ResponseMessage.LEFT_VOICE)
        return
    await interaction.response.send_message(status)
