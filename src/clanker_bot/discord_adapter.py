"""Discord-specific adapter utilities."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import discord


@dataclass
class VoiceSessionState:
    """Tracks the current voice session state."""

    active_channel_id: int | None = None
    voice_client: discord.VoiceClient | None = None

    def is_busy(self) -> bool:
        return self.voice_client is not None


class VoiceSessionManager:
    """Manages a single active voice session."""

    def __init__(self) -> None:
        self.state = VoiceSessionState()
        self._lock = asyncio.Lock()

    @property
    def active_channel_id(self) -> int | None:
        return self.state.active_channel_id

    @property
    def voice_client(self) -> discord.VoiceClient | None:
        return self.state.voice_client

    def is_busy(self) -> bool:
        return self.state.is_busy()

    async def join(
        self,
        channel: discord.VoiceChannel | discord.StageChannel,
        *,
        voice_client_cls: type[discord.VoiceClient] | None = None,
    ) -> tuple[bool, str]:
        async with self._lock:
            if self.state.is_busy():
                return False, "BUSY"
            if voice_client_cls:
                voice_client = await channel.connect(cls=voice_client_cls)
            else:
                voice_client = await channel.connect()
            self.state.voice_client = voice_client
            self.state.active_channel_id = channel.id
            return True, "OK"

    async def leave(self) -> tuple[bool, str]:
        async with self._lock:
            if not self.state.voice_client:
                return False, "NOT_CONNECTED"
            await self.state.voice_client.disconnect()
            self.state.voice_client = None
            self.state.active_channel_id = None
            return True, "OK"
