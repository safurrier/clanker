"""Voice connection resilience utilities.

Provides:
- VoiceKeepalive: Sends silence packets to prevent Discord load-balancer disconnects
- VoiceReconnector: Handles unexpected disconnects and attempts to rejoin
- create_reconnect_handler: Creates an `after` callback for voice_recv.listen()

Usage:
    # Start keepalive after joining voice
    keepalive = VoiceKeepalive(voice_client)
    keepalive.start()

    # Set up reconnection handling
    reconnector = VoiceReconnector(rejoin_callback=my_rejoin_function)
    handler = create_reconnect_handler(
        lambda err: reconnector.handle_disconnect(guild_id, channel_id, err)
    )
    voice_client.listen(sink, after=handler)

    # Mark expected disconnects (e.g., /leave command)
    reconnector.mark_expected_disconnect(guild_id)
    await voice_manager.leave()
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from loguru import logger

# Opus silence frame - Discord's voice protocol recognizes this as valid audio
# without producing any audible sound
OPUS_SILENCE_FRAME = b"\xf8\xff\xfe"

# Default keepalive interval (seconds)
DEFAULT_KEEPALIVE_INTERVAL = 15.0

# Default reconnection settings
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5.0


@dataclass
class VoiceKeepalive:
    """Sends periodic silence packets to keep voice connection alive.

    Discord's load balancer disconnects idle voice clients after 15 minutes
    to 2 hours. Sending silence packets prevents this.

    Args:
        voice_client: The Discord voice client to keep alive.
        interval_seconds: Time between silence packets (default: 15s).
    """

    voice_client: object  # discord.VoiceClient, but we accept any duck-typed object
    interval_seconds: float = DEFAULT_KEEPALIVE_INTERVAL
    _task: asyncio.Task[None] | None = field(default=None, init=False)

    def start(self) -> None:
        """Start the keepalive background task."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._keepalive_loop())
        logger.debug(
            "voice_keepalive.started: interval={}s",
            self.interval_seconds,
        )

    def stop(self) -> None:
        """Stop the keepalive background task."""
        if self._task is None:
            return
        self._task.cancel()
        self._task = None
        logger.debug("voice_keepalive.stopped")

    async def _keepalive_loop(self) -> None:
        """Background loop that sends silence packets."""
        try:
            while True:
                # Check if still connected
                is_connected = getattr(self.voice_client, "is_connected", lambda: False)
                if not is_connected():
                    logger.debug("voice_keepalive.disconnected: stopping loop")
                    break

                # Send silence packet
                try:
                    send_audio_packet = getattr(
                        self.voice_client, "send_audio_packet", None
                    )
                    if send_audio_packet:
                        send_audio_packet(OPUS_SILENCE_FRAME, encode=False)
                        logger.debug("voice_keepalive.sent_silence")
                except Exception as e:
                    logger.warning("voice_keepalive.send_error: {}", e)

                await asyncio.sleep(self.interval_seconds)

        except asyncio.CancelledError:
            logger.debug("voice_keepalive.cancelled")
        finally:
            self._task = None


def create_reconnect_handler(
    on_disconnect: Callable[[Exception | None], Awaitable[None]],
) -> Callable[[Exception | None], None]:
    """Create an `after` callback for voice_recv.listen().

    The returned function is called by voice_recv when the audio sink stops,
    either due to an error or normal exhaustion. It bridges the sync callback
    to your async disconnect handler.

    Args:
        on_disconnect: Async function to call when disconnect occurs.
                      Receives the error (or None if no error).

    Returns:
        A sync callback suitable for voice_recv.listen(sink, after=callback).

    Example:
        handler = create_reconnect_handler(
            lambda err: reconnector.handle_disconnect(guild_id, channel_id, err)
        )
        voice_client.listen(sink, after=handler)
    """

    def handler(error: Exception | None) -> None:
        logger.debug(
            "voice_reconnect.handler_called: error={}",
            type(error).__name__ if error else None,
        )

        # Bridge to async world
        async def run_callback() -> None:
            try:
                await on_disconnect(error)
            except Exception as e:
                logger.exception("voice_reconnect.callback_error: {}", e)

        # Schedule the async callback
        try:
            loop = asyncio.get_running_loop()
            # Store reference to prevent garbage collection (required by RUF006)
            task = loop.create_task(run_callback())
            # Fire-and-forget: we don't need the result but must reference the task
            task.add_done_callback(lambda _: None)
        except RuntimeError:
            # No running loop - create one for the callback
            logger.warning(
                "voice_reconnect.no_event_loop: running callback in new loop"
            )
            asyncio.run(run_callback())

    return handler


@dataclass
class VoiceReconnector:
    """Manages voice reconnection after unexpected disconnects.

    Tracks expected vs unexpected disconnects and attempts to rejoin
    the voice channel on unexpected disconnects.

    Args:
        rejoin_callback: Async function to rejoin voice.
                        Takes (guild_id, channel_id), returns bool (success).
        max_retries: Maximum reconnection attempts (default: 3).
        retry_delay_seconds: Delay between retries (default: 5s).
    """

    rejoin_callback: Callable[[int, int], Awaitable[bool]]
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY
    _expected_disconnects: set[int] = field(default_factory=set)

    def mark_expected_disconnect(self, guild_id: int) -> None:
        """Mark that we're intentionally disconnecting from a guild.

        Call this before running /leave or other intentional disconnects
        to prevent reconnection attempts.
        """
        self._expected_disconnects.add(guild_id)
        logger.debug("voice_reconnect.marked_expected: guild={}", guild_id)

    def is_expected_disconnect(self, guild_id: int) -> bool:
        """Check if a disconnect for this guild is expected."""
        return guild_id in self._expected_disconnects

    async def handle_disconnect(
        self,
        guild_id: int,
        channel_id: int,
        error: Exception | None,
    ) -> None:
        """Handle a voice disconnect event.

        If the disconnect was expected (marked via mark_expected_disconnect),
        clears the flag and does nothing. Otherwise, attempts to rejoin.

        Args:
            guild_id: The guild ID where disconnect occurred.
            channel_id: The channel ID to rejoin.
            error: The error that caused disconnect (or None if normal stop).
        """
        # Check if this was expected
        if guild_id in self._expected_disconnects:
            self._expected_disconnects.discard(guild_id)
            logger.info(
                "voice_reconnect.expected_disconnect: guild={}, skipping rejoin",
                guild_id,
            )
            return

        # Unexpected disconnect - attempt to rejoin
        logger.warning(
            "voice_reconnect.unexpected_disconnect: guild={}, channel={}, error={}",
            guild_id,
            channel_id,
            type(error).__name__ if error else None,
        )

        await self._attempt_rejoin(guild_id, channel_id)

    async def _attempt_rejoin(self, guild_id: int, channel_id: int) -> None:
        """Attempt to rejoin voice channel with retries."""
        for attempt in range(1, self.max_retries + 1):
            logger.info(
                "voice_reconnect.attempting_rejoin: guild={}, channel={}, attempt={}/{}",
                guild_id,
                channel_id,
                attempt,
                self.max_retries,
            )

            try:
                success = await self.rejoin_callback(guild_id, channel_id)
                if success:
                    logger.info(
                        "voice_reconnect.rejoin_success: guild={}, attempt={}",
                        guild_id,
                        attempt,
                    )
                    return
                else:
                    logger.warning(
                        "voice_reconnect.rejoin_failed: guild={}, attempt={}",
                        guild_id,
                        attempt,
                    )
            except Exception as e:
                logger.exception(
                    "voice_reconnect.rejoin_error: guild={}, attempt={}, error={}",
                    guild_id,
                    attempt,
                    e,
                )

            # Wait before retry (unless this was the last attempt)
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay_seconds)

        logger.error(
            "voice_reconnect.gave_up: guild={}, channel={}, max_retries={}",
            guild_id,
            channel_id,
            self.max_retries,
        )
