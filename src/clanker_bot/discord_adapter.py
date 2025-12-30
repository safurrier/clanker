"""Discord-specific adapter utilities."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum

import discord
from loguru import logger

from .voice_resilience import VoiceReconnector


class VoiceStatus(str, Enum):
    """Status codes for voice session operations."""

    OK = "OK"
    BUSY = "BUSY"
    NOT_CONNECTED = "NOT_CONNECTED"


@dataclass
class VoiceSessionState:
    """Tracks the current voice session state."""

    active_channel_id: int | None = None
    active_guild_id: int | None = None
    voice_client: discord.VoiceClient | None = None

    def is_busy(self) -> bool:
        return self.voice_client is not None


class VoiceSessionManager:
    """Manages a single active voice session with reconnection support."""

    def __init__(self) -> None:
        self.state = VoiceSessionState()
        self._lock = asyncio.Lock()
        self._reconnector: VoiceReconnector | None = None
        self._ingest_session: object | None = None  # VoiceIngestSession, set externally

    @property
    def active_channel_id(self) -> int | None:
        return self.state.active_channel_id

    @property
    def active_guild_id(self) -> int | None:
        return self.state.active_guild_id

    @property
    def voice_client(self) -> discord.VoiceClient | None:
        return self.state.voice_client

    @property
    def reconnector(self) -> VoiceReconnector | None:
        return self._reconnector

    def set_reconnector(self, reconnector: VoiceReconnector) -> None:
        """Set the reconnector for handling unexpected disconnects."""
        self._reconnector = reconnector

    def set_ingest_session(self, session: object | None) -> None:
        """Set the current voice ingest session for cleanup."""
        self._ingest_session = session

    def is_busy(self) -> bool:
        return self.state.is_busy()

    async def join(
        self,
        channel: discord.VoiceChannel | discord.StageChannel,
        *,
        voice_client_cls: type[discord.VoiceClient] | None = None,
    ) -> tuple[bool, VoiceStatus]:
        async with self._lock:
            if self.state.is_busy():
                return False, VoiceStatus.BUSY
            if voice_client_cls:
                voice_client = await channel.connect(cls=voice_client_cls)
            else:
                voice_client = await channel.connect()
            self.state.voice_client = voice_client
            self.state.active_channel_id = channel.id
            self.state.active_guild_id = channel.guild.id
            logger.debug(
                "voice_manager.joined: guild={}, channel={}",
                channel.guild.id,
                channel.id,
            )
            return True, VoiceStatus.OK

    async def leave(self) -> tuple[bool, VoiceStatus]:
        async with self._lock:
            if not self.state.voice_client:
                return False, VoiceStatus.NOT_CONNECTED

            # Mark as expected disconnect to prevent reconnection attempts
            if self._reconnector and self.state.active_guild_id:
                self._reconnector.mark_expected_disconnect(self.state.active_guild_id)

            # Cleanup ingest session
            if self._ingest_session is not None:
                cleanup = getattr(self._ingest_session, "cleanup", None)
                if cleanup:
                    cleanup()
                self._ingest_session = None

            guild_id = self.state.active_guild_id
            channel_id = self.state.active_channel_id

            await self.state.voice_client.disconnect()
            self.state.voice_client = None
            self.state.active_channel_id = None
            self.state.active_guild_id = None

            logger.debug(
                "voice_manager.left: guild={}, channel={}",
                guild_id,
                channel_id,
            )
            return True, VoiceStatus.OK

    def clear_state(self) -> None:
        """Clear voice state without disconnecting (for use after unexpected disconnect)."""
        if self._ingest_session is not None:
            cleanup = getattr(self._ingest_session, "cleanup", None)
            if cleanup:
                cleanup()
            self._ingest_session = None
        self.state.voice_client = None
        self.state.active_channel_id = None
        self.state.active_guild_id = None
        logger.debug("voice_manager.state_cleared")
