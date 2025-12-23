"""Voice-related command handlers."""

from __future__ import annotations

import logging
from typing import cast

import discord
import discord.ext.voice_recv as voice_recv

from ..voice_ingest import start_voice_ingest, voice_client_cls
from .types import BotDependencies


async def handle_join(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    logger = logging.getLogger(__name__)
    if deps.admin_state and not deps.admin_state.allow_new_meetings:
        await interaction.response.send_message("New meetings are disabled.")
        return
    if not interaction.user:
        await interaction.response.send_message("Unable to resolve voice channel.")
        return
    voice_state = getattr(interaction.user, "voice", None)
    voice_channel = getattr(voice_state, "channel", None)
    if not voice_state or not voice_channel:
        await interaction.response.send_message("Join a voice channel first.")
        return
    ingest_voice_client_cls = None
    if deps.voice_ingest_enabled:
        ingest_voice_client_cls = voice_client_cls()
    ok, status = await deps.voice_manager.join(
        voice_channel, voice_client_cls=ingest_voice_client_cls
    )
    if ok:
        response = "Joined voice channel."
        if deps.voice_ingest_enabled:
            if deps.stt is None:
                response += " (Transcription unavailable; STT not configured.)"
            elif ingest_voice_client_cls is None:
                response += " (Transcription unavailable in this host build.)"
            else:
                try:
                    voice_client = deps.voice_manager.voice_client
                    if voice_client is None:
                        raise RuntimeError("Voice client not available.")
                    # Safe cast: we just joined with voice_recv.VoiceRecvClient class
                    recv_client = cast(voice_recv.VoiceRecvClient, voice_client)
                    await start_voice_ingest(recv_client, deps.stt)
                    response += " (Transcription enabled.)"
                except Exception:
                    logger.exception("Failed to start voice ingest.")
                    response += " (Transcription unavailable due to setup error.)"
        await interaction.response.send_message(response)
        return
    await interaction.response.send_message(status)


async def handle_leave(
    interaction: discord.Interaction,
    deps: BotDependencies,
) -> None:
    ok, status = await deps.voice_manager.leave()
    if ok:
        await interaction.response.send_message("Left voice channel.")
        return
    await interaction.response.send_message(status)
