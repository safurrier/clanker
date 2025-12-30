"""Voice-related command handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import discord
import discord.ext.voice_recv as voice_recv
from loguru import logger

from ..voice_ingest import TranscriptBuffer, start_voice_ingest, voice_client_cls
from ..voice_resilience import create_reconnect_handler
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


def _create_transcript_callback(
    guild_id: int,
    transcript_buffer: TranscriptBuffer | None,
):
    """Create a callback that adds transcript events to the buffer."""
    from clanker.voice.worker import TranscriptEvent

    async def on_transcript(event: TranscriptEvent) -> None:
        if transcript_buffer is None:
            logger.debug(
                "voice.transcript_callback: no buffer, event discarded: {}",
                event.text[:50] if event.text else "",
            )
            return
        transcript_buffer.add(guild_id, event)
        logger.debug(
            "voice.transcript_added: guild={}, speaker={}, text={}",
            guild_id,
            event.speaker_id,
            event.text[:50] if event.text else "",
        )

    return on_transcript


async def _setup_transcription(
    deps: BotDependencies,
    voice_client_cls: type[discord.VoiceClient] | None,
    guild_id: int | None,
    channel_id: int | None,
) -> str:
    """Set up transcription and return status message."""
    logger.debug(
        "voice.transcription_setup: enabled={}, stt={}, buffer={}, guild={}, channel={}",
        deps.voice_ingest_enabled,
        deps.stt is not None,
        deps.transcript_buffer is not None,
        guild_id,
        channel_id,
    )

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

        # Create callback to populate transcript buffer
        on_transcript = None
        if guild_id is not None:
            on_transcript = _create_transcript_callback(
                guild_id, deps.transcript_buffer
            )

        # Create disconnect handler for reconnection
        on_disconnect = None
        if guild_id is not None and channel_id is not None:
            on_disconnect = _create_disconnect_handler(deps, guild_id, channel_id)

        session = await start_voice_ingest(
            recv_client,
            deps.stt,
            on_transcript=on_transcript,
            on_disconnect=on_disconnect,
        )

        # Store session for cleanup
        deps.voice_manager.set_ingest_session(session)

        logger.debug("voice.ingest_started: guild={}", guild_id)
        return (
            f"{ResponseMessage.JOINED_VOICE} ({ResponseMessage.TRANSCRIPTION_ENABLED})"
        )
    except Exception:
        logger.exception("Failed to start voice ingest.")
        return f"{ResponseMessage.JOINED_VOICE} ({ResponseMessage.TRANSCRIPTION_SETUP_ERROR})"


def _create_disconnect_handler(
    deps: BotDependencies,
    guild_id: int,
    channel_id: int,
) -> Callable[[Exception | None], None]:
    """Create a disconnect handler for voice reconnection."""

    async def handle_disconnect(error: Exception | None) -> None:
        """Handle unexpected voice disconnect."""
        reconnector = deps.voice_manager.reconnector
        if reconnector is None:
            logger.warning(
                "voice.disconnect_no_reconnector: guild={}, error={}",
                guild_id,
                type(error).__name__ if error else None,
            )
            # Just clear state since we can't reconnect
            deps.voice_manager.clear_state()
            return

        await reconnector.handle_disconnect(guild_id, channel_id, error)

    return create_reconnect_handler(handle_disconnect)


async def join_voice_channel(
    voice_channel: discord.VoiceChannel | discord.StageChannel,
    deps: BotDependencies,
    guild_id: int | None = None,
) -> tuple[bool, str]:
    """Join a voice channel and set up transcription.

    This is the core join logic, usable from slash commands or nudge buttons.

    Args:
        voice_channel: The voice channel to join.
        deps: Bot dependencies.
        guild_id: Guild ID for transcript buffer (optional).

    Returns:
        Tuple of (success, status_message).
    """
    logger.debug(
        "voice.joining_channel: channel={}, channel_name={}",
        voice_channel.id,
        voice_channel.name,
    )

    # Join the voice channel
    vc_cls = _get_voice_client_cls(deps)
    ok, status = await deps.voice_manager.join(voice_channel, voice_client_cls=vc_cls)

    if not ok:
        logger.debug("voice.join_failed: status={}", status)
        return False, str(status)

    logger.debug("voice.joined_channel: channel={}", voice_channel.id)

    # Setup transcription with reconnection support
    message = await _setup_transcription(
        deps, vc_cls, guild_id, channel_id=voice_channel.id
    )
    return True, message


async def handle_join(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    user_id = interaction.user.id if interaction.user else None
    guild_id = interaction.guild_id
    logger.debug(
        "voice.join_requested: user={}, guild={}",
        user_id,
        guild_id,
    )

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

    # Defer response - transcription setup can take >3s (Silero VAD loading)
    await interaction.response.defer()

    # Use core join logic
    ok, message = await join_voice_channel(voice_channel, deps, guild_id)
    await interaction.followup.send(message)


async def handle_leave(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    ok, status = await deps.voice_manager.leave()
    if ok:
        await interaction.response.send_message(ResponseMessage.LEFT_VOICE)
        return
    await interaction.response.send_message(status)
