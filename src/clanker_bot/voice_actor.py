"""Actor-based voice connection management.

This module provides a message-passing actor model for voice connections,
replacing the callback-based approach in voice_ingest.py and voice_resilience.py.

Enable with: USE_VOICE_ACTOR=1

The actor model provides:
- Single source of truth for voice state
- Sequential message processing (no race conditions)
- Thread-safe audio ingestion via Queue.put_nowait()
- Complete audit trail via message logging
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, cast

import discord
import discord.ext.voice_recv as voice_recv
from loguru import logger

from clanker.providers.audio_utils import convert_pcm
from clanker.providers.base import STT
from clanker.voice.formats import DISCORD_FORMAT, SDK_FORMAT
from clanker.voice.vad import SpeechDetector, resolve_detector
from clanker.voice.worker import TranscriptEvent, transcript_loop_once

from .voice_ingest import TranscriptBuffer

if TYPE_CHECKING:
    pass

# Feature flag for gradual rollout
USE_VOICE_ACTOR = os.getenv("USE_VOICE_ACTOR", "0") == "1"

# Constants
DEFAULT_KEEPALIVE_INTERVAL = 15.0
DEFAULT_PROCESS_INTERVAL = 1.0
DEFAULT_HEALTH_CHECK_INTERVAL = 10.0
DEFAULT_STALE_THRESHOLD_SECONDS = 120.0
DEFAULT_RECONNECT_MAX_RETRIES = 3
DEFAULT_RECONNECT_DELAY_SECONDS = 5.0
OPUS_SILENCE_FRAME = b"\xf8\xff\xfe"


class VoiceStatus(str, Enum):
    """Voice connection status."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STALE = "stale"
    RECONNECTING = "reconnecting"


# --- Message Types ---
# All messages are frozen dataclasses for immutability and debuggability.


@dataclass(frozen=True)
class JoinRequest:
    """Request to join a voice channel."""

    channel_id: int
    guild_id: int
    response_queue: asyncio.Queue  # Queue[JoinResult]


@dataclass(frozen=True)
class LeaveRequest:
    """Request to leave voice channel."""

    response_queue: asyncio.Queue  # Queue[LeaveResult]


@dataclass(frozen=True)
class AudioReceived:
    """Audio packet received from Discord."""

    user_id: int
    pcm_bytes: bytes
    timestamp: datetime


@dataclass(frozen=True)
class StaleTimeout:
    """Health check detected no audio for too long."""

    silence_seconds: float


@dataclass(frozen=True)
class DisconnectDetected:
    """voice_recv reported a disconnect."""

    error: Exception | None


@dataclass(frozen=True)
class ReconnectAttempt:
    """Time to try reconnecting."""

    attempt: int


@dataclass(frozen=True)
class SendKeepalive:
    """Timer fired, send silence packet."""

    pass


@dataclass(frozen=True)
class ProcessBuffers:
    """Timer fired, run STT on buffered audio."""

    pass


# Union type for type checking
VoiceMessage = (
    JoinRequest
    | LeaveRequest
    | AudioReceived
    | StaleTimeout
    | DisconnectDetected
    | ReconnectAttempt
    | SendKeepalive
    | ProcessBuffers
)


# --- Result Types ---


@dataclass(frozen=True)
class JoinResult:
    """Result of a join request."""

    success: bool
    error: str | None = None


@dataclass(frozen=True)
class LeaveResult:
    """Result of a leave request."""

    success: bool
    error: str | None = None


# --- Audio Buffer ---


@dataclass
class AudioBuffer:
    """Buffer for a single user's audio."""

    pcm_bytes: bytearray = field(default_factory=bytearray)
    start_time: datetime | None = None


# --- Voice Actor ---


@dataclass
class VoiceActor:
    """Actor that manages voice connection via message passing.

    All voice operations go through the message queue, ensuring:
    - Sequential processing (no race conditions)
    - Thread-safe audio ingestion (Queue.put_nowait)
    - Complete audit trail (message log)

    Usage:
        actor = VoiceActor(bot=bot, stt=stt_provider)
        asyncio.create_task(actor.run())

        result = await actor.join(channel_id=123, guild_id=456)
    """

    bot: discord.Client
    stt: STT
    detector: SpeechDetector | None = None

    # Configuration
    keepalive_interval: float = DEFAULT_KEEPALIVE_INTERVAL
    process_interval: float = DEFAULT_PROCESS_INTERVAL
    health_check_interval: float = DEFAULT_HEALTH_CHECK_INTERVAL
    stale_threshold_seconds: float = DEFAULT_STALE_THRESHOLD_SECONDS
    reconnect_max_retries: int = DEFAULT_RECONNECT_MAX_RETRIES
    reconnect_delay_seconds: float = DEFAULT_RECONNECT_DELAY_SECONDS
    chunk_seconds: float = 7.5
    idle_timeout_seconds: float = 3.0
    max_silence_ms: int = 1000
    min_utterance_ms: int = 500
    sample_rate_hz: int = 48000

    # Message queue
    _inbox: asyncio.Queue[VoiceMessage] = field(default_factory=asyncio.Queue)

    # --- Internal State (all managed by _handle methods) ---
    _status: VoiceStatus = field(default=VoiceStatus.DISCONNECTED, init=False)
    _guild_id: int | None = field(default=None, init=False)
    _channel_id: int | None = field(default=None, init=False)
    _voice_client: voice_recv.VoiceRecvClient | None = field(default=None, init=False)
    _audio_buffers: dict[int, AudioBuffer] = field(default_factory=dict, init=False)
    _last_audio_time: datetime | None = field(default=None, init=False)
    _reconnect_attempt: int = field(default=0, init=False)
    _transcript_buffer: TranscriptBuffer = field(
        default_factory=TranscriptBuffer, init=False
    )
    _stale_posted: bool = field(default=False, init=False)
    _timer_tasks: list[asyncio.Task] = field(default_factory=list, init=False)
    _on_transcript: Callable[[TranscriptEvent], Awaitable[None]] | None = field(
        default=None, init=False
    )
    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Initialize detector if not provided."""
        if self.detector is None:
            self.detector = resolve_detector()

    # --- Read-only Properties ---

    @property
    def status(self) -> VoiceStatus:
        """Current connection status (read-only)."""
        return self._status

    @property
    def guild_id(self) -> int | None:
        """Current guild ID (read-only)."""
        return self._guild_id

    @property
    def channel_id(self) -> int | None:
        """Current channel ID (read-only)."""
        return self._channel_id

    @property
    def voice_client(self) -> voice_recv.VoiceRecvClient | None:
        """Current voice client (read-only)."""
        return self._voice_client

    # --- Public API ---

    async def join(self, channel_id: int, guild_id: int) -> JoinResult:
        """Request to join a voice channel.

        Posts JoinRequest to inbox and waits for result.
        Thread-safe: can be called from any coroutine.

        Args:
            channel_id: Discord channel ID to join.
            guild_id: Discord guild ID.

        Returns:
            JoinResult with success status and optional error.
        """
        response_queue: asyncio.Queue[JoinResult] = asyncio.Queue()
        await self._inbox.put(
            JoinRequest(
                channel_id=channel_id,
                guild_id=guild_id,
                response_queue=response_queue,
            )
        )
        return await response_queue.get()

    async def leave(self) -> LeaveResult:
        """Request to leave voice channel.

        Posts LeaveRequest to inbox and waits for result.

        Returns:
            LeaveResult with success status and optional error.
        """
        response_queue: asyncio.Queue[LeaveResult] = asyncio.Queue()
        await self._inbox.put(LeaveRequest(response_queue=response_queue))
        return await response_queue.get()

    def post_audio(self, user_id: int, pcm_bytes: bytes) -> None:
        """Post audio data from voice_recv thread.

        IMPORTANT: This is called from the voice_recv thread, not the
        bot's event loop. Uses call_soon_threadsafe to safely marshal
        the message onto the event loop.

        Args:
            user_id: Discord user ID who spoke.
            pcm_bytes: Raw PCM audio bytes (mono, 48kHz, 16-bit).
        """
        msg = AudioReceived(
            user_id=user_id,
            pcm_bytes=pcm_bytes,
            timestamp=datetime.now(),
        )
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._inbox.put_nowait, msg)
        else:
            self._inbox.put_nowait(msg)

    def post_disconnect(self, error: Exception | None) -> None:
        """Post disconnect event from voice_recv after callback.

        Thread-safe: uses call_soon_threadsafe to marshal onto event loop.

        Args:
            error: The error that caused disconnect, or None.
        """
        msg = DisconnectDetected(error=error)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._inbox.put_nowait, msg)
        else:
            self._inbox.put_nowait(msg)

    def get_transcripts(self, guild_id: int) -> list[TranscriptEvent]:
        """Get recent transcripts for a guild.

        Read-only access to transcript buffer.

        Args:
            guild_id: Discord guild ID.

        Returns:
            List of recent transcript events.
        """
        return self._transcript_buffer.get(guild_id)

    def set_transcript_callback(
        self, callback: Callable[[TranscriptEvent], Awaitable[None]] | None
    ) -> None:
        """Set callback for transcript events.

        Args:
            callback: Async function to call with each transcript event.
        """
        self._on_transcript = callback

    # --- Main Loop ---

    async def run(self) -> None:
        """Main actor loop. Process messages sequentially.

        Call once at startup:
            asyncio.create_task(actor.run())

        The loop runs forever until cancelled.
        """
        self._loop = asyncio.get_running_loop()
        logger.info("voice_actor.started")

        # Start timer tasks
        self._timer_tasks = [
            asyncio.create_task(self._keepalive_timer()),
            asyncio.create_task(self._process_timer()),
            asyncio.create_task(self._health_timer()),
        ]

        try:
            while True:
                msg = await self._inbox.get()
                await self._handle(msg)
        except asyncio.CancelledError:
            logger.info("voice_actor.stopping")
            # Cancel timer tasks
            for task in self._timer_tasks:
                task.cancel()
            # Cleanup voice client
            if self._voice_client and self._voice_client.is_connected():
                await self._voice_client.disconnect()
            logger.info("voice_actor.stopped")
            raise

    async def _handle(self, msg: VoiceMessage) -> None:
        """Handle a single message. ALL state changes happen here.

        Args:
            msg: The message to process.
        """
        logger.debug(
            "voice.msg: status={}, msg={}",
            self._status.value,
            type(msg).__name__,
        )

        match msg:
            case JoinRequest(channel_id, guild_id, response_queue):
                result = await self._handle_join(channel_id, guild_id)
                await response_queue.put(result)

            case LeaveRequest(response_queue):
                result = await self._handle_leave()
                await response_queue.put(result)

            case AudioReceived(user_id, pcm_bytes, timestamp):
                self._handle_audio(user_id, pcm_bytes, timestamp)

            case StaleTimeout(silence_seconds):
                await self._handle_stale(silence_seconds)

            case DisconnectDetected(error):
                await self._handle_disconnect(error)

            case ReconnectAttempt(attempt):
                await self._handle_reconnect(attempt)

            case SendKeepalive():
                self._handle_keepalive()

            case ProcessBuffers():
                await self._handle_process_buffers()

    # --- Message Handlers ---

    async def _handle_join(self, channel_id: int, guild_id: int) -> JoinResult:
        """Handle JoinRequest message.

        Transitions: DISCONNECTED → CONNECTING → CONNECTED

        Args:
            channel_id: Discord channel ID.
            guild_id: Discord guild ID.

        Returns:
            JoinResult with success status.
        """
        if self._status != VoiceStatus.DISCONNECTED:
            return JoinResult(
                success=False,
                error=f"Cannot join: already {self._status.value}",
            )

        self._status = VoiceStatus.CONNECTING
        logger.info("voice_actor.joining: guild={}, channel={}", guild_id, channel_id)

        try:
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.VoiceChannel | discord.StageChannel):
                self._status = VoiceStatus.DISCONNECTED
                return JoinResult(success=False, error="Channel not found")

            # Connect with voice_recv client for audio capture
            self._voice_client = cast(
                voice_recv.VoiceRecvClient,
                await channel.connect(cls=voice_recv.VoiceRecvClient),
            )

            # Set up audio sink that posts to this actor
            sink = VoiceActorSink(self)
            self._voice_client.listen(sink, after=self._create_after_callback())

            self._channel_id = channel_id
            self._guild_id = guild_id
            self._status = VoiceStatus.CONNECTED
            self._last_audio_time = None
            self._stale_posted = False

            logger.info(
                "voice_actor.connected: guild={}, channel={}",
                guild_id,
                channel_id,
            )
            return JoinResult(success=True)

        except Exception as e:
            logger.exception("voice_actor.join_error: {}", e)
            self._status = VoiceStatus.DISCONNECTED
            return JoinResult(success=False, error=str(e))

    def _create_after_callback(self) -> Callable[[Exception | None], None]:
        """Create the after callback for voice_recv.listen().

        Returns a sync callback that posts DisconnectDetected to the actor.
        """

        def after_callback(error: Exception | None) -> None:
            logger.debug(
                "voice_actor.after_callback: error={}",
                type(error).__name__ if error else None,
            )
            self.post_disconnect(error)

        return after_callback

    async def _handle_leave(self) -> LeaveResult:
        """Handle LeaveRequest message.

        Transitions: any → DISCONNECTED

        Returns:
            LeaveResult with success status.
        """
        if self._status == VoiceStatus.DISCONNECTED:
            return LeaveResult(success=False, error="Not connected")

        guild_id = self._guild_id
        channel_id = self._channel_id

        logger.info(
            "voice_actor.leaving: guild={}, channel={}",
            guild_id,
            channel_id,
        )

        try:
            if self._voice_client and self._voice_client.is_connected():
                await self._voice_client.disconnect()
        except Exception as e:
            logger.warning("voice_actor.disconnect_error: {}", e)

        self._clear_state()

        logger.info(
            "voice_actor.left: guild={}, channel={}",
            guild_id,
            channel_id,
        )
        return LeaveResult(success=True)

    def _handle_audio(
        self, user_id: int, pcm_bytes: bytes, timestamp: datetime
    ) -> None:
        """Handle AudioReceived message.

        Buffers audio for the user and updates last_audio_time.

        Args:
            user_id: Discord user ID.
            pcm_bytes: Raw PCM audio bytes.
            timestamp: When the audio was received.
        """
        if self._status != VoiceStatus.CONNECTED:
            return  # Ignore audio in other states

        # Get or create buffer for user
        if user_id not in self._audio_buffers:
            self._audio_buffers[user_id] = AudioBuffer(start_time=timestamp)

        buffer = self._audio_buffers[user_id]
        if buffer.start_time is None:
            buffer.start_time = timestamp
        buffer.pcm_bytes.extend(pcm_bytes)

        self._last_audio_time = timestamp
        self._stale_posted = False  # Reset stale flag on audio

    async def _handle_stale(self, silence_seconds: float) -> None:
        """Handle StaleTimeout message.

        Transitions: CONNECTED → RECONNECTING

        Args:
            silence_seconds: How long audio has been silent.
        """
        if self._status != VoiceStatus.CONNECTED:
            return  # Only care about stale when connected

        logger.warning(
            "voice_actor.stale: silence_seconds={:.1f}, initiating reconnect",
            silence_seconds,
        )

        self._status = VoiceStatus.RECONNECTING
        self._reconnect_attempt = 0

        # Disconnect current client
        if self._voice_client and self._voice_client.is_connected():
            try:
                await self._voice_client.disconnect()
            except Exception as e:
                logger.warning("voice_actor.stale_disconnect_error: {}", e)

        self._voice_client = None

        # Post first reconnect attempt
        await self._inbox.put(ReconnectAttempt(attempt=1))

    async def _handle_disconnect(self, error: Exception | None) -> None:
        """Handle DisconnectDetected message.

        Called when voice_recv's after callback fires.

        Args:
            error: The error that caused disconnect, or None.
        """
        # If we're already disconnected or reconnecting, ignore
        if self._status in (VoiceStatus.DISCONNECTED, VoiceStatus.RECONNECTING):
            return

        # If this was an intentional leave, we would have transitioned to DISCONNECTED
        # before the after callback fired. So if we're still CONNECTED, it's unexpected.
        if self._status == VoiceStatus.CONNECTED:
            logger.warning(
                "voice_actor.unexpected_disconnect: error={}",
                type(error).__name__ if error else None,
            )

            self._status = VoiceStatus.RECONNECTING
            self._reconnect_attempt = 0
            self._voice_client = None

            # Post first reconnect attempt
            await self._inbox.put(ReconnectAttempt(attempt=1))

    async def _handle_reconnect(self, attempt: int) -> None:
        """Handle ReconnectAttempt message.

        Attempts to reconnect to the voice channel.

        Args:
            attempt: Which attempt number this is (1-indexed).
        """
        if self._status != VoiceStatus.RECONNECTING:
            return  # State changed, abort reconnect

        if attempt > self.reconnect_max_retries:
            logger.error(
                "voice_actor.reconnect_failed: max_retries={} exceeded",
                self.reconnect_max_retries,
            )
            self._clear_state()
            return

        logger.info(
            "voice_actor.reconnect_attempt: attempt={}/{}, guild={}, channel={}",
            attempt,
            self.reconnect_max_retries,
            self._guild_id,
            self._channel_id,
        )

        try:
            if self._channel_id is None:
                raise ValueError("No channel ID to reconnect to")

            channel = self.bot.get_channel(self._channel_id)
            if not isinstance(channel, discord.VoiceChannel | discord.StageChannel):
                raise ValueError("Channel not found")

            # Disconnect any stale voice client at the guild level
            # Discord.py tracks voice clients per-guild, so we must clear it first
            guild = channel.guild
            if guild.voice_client is not None:
                logger.debug(
                    "voice_actor.disconnecting_stale_client: guild={}",
                    self._guild_id,
                )
                try:
                    await guild.voice_client.disconnect(force=True)
                except Exception as e:
                    logger.warning(
                        "voice_actor.stale_disconnect_error: guild={}, error={}",
                        self._guild_id,
                        e,
                    )

            self._voice_client = cast(
                voice_recv.VoiceRecvClient,
                await channel.connect(cls=voice_recv.VoiceRecvClient),
            )

            # Set up audio sink
            sink = VoiceActorSink(self)
            self._voice_client.listen(sink, after=self._create_after_callback())

            self._status = VoiceStatus.CONNECTED
            self._last_audio_time = None
            self._stale_posted = False
            self._reconnect_attempt = 0

            logger.info(
                "voice_actor.reconnect_success: attempt={}, guild={}, channel={}",
                attempt,
                self._guild_id,
                self._channel_id,
            )

        except Exception as e:
            logger.warning(
                "voice_actor.reconnect_error: attempt={}, error={}",
                attempt,
                e,
            )

            # Schedule next attempt after delay
            await asyncio.sleep(self.reconnect_delay_seconds)
            await self._inbox.put(ReconnectAttempt(attempt=attempt + 1))

    def _handle_keepalive(self) -> None:
        """Handle SendKeepalive message.

        Sends a silence packet to keep the connection alive.
        """
        if self._status != VoiceStatus.CONNECTED:
            return

        if self._voice_client and self._voice_client.is_connected():
            try:
                self._voice_client.send_audio_packet(OPUS_SILENCE_FRAME, encode=False)
                logger.debug("voice_actor.keepalive_sent")
            except Exception as e:
                logger.warning("voice_actor.keepalive_error: {}", e)

    async def _handle_process_buffers(self) -> None:
        """Handle ProcessBuffers message.

        Runs STT pipeline on buffered audio if conditions are met.
        """
        if self._status != VoiceStatus.CONNECTED:
            return

        if not self._should_process():
            return

        # Extract buffers
        payload = {}
        for user_id, buffer in self._audio_buffers.items():
            if buffer.pcm_bytes:
                from clanker.voice.worker import AudioBuffer as WorkerAudioBuffer

                payload[user_id] = WorkerAudioBuffer(
                    pcm_bytes=bytes(buffer.pcm_bytes),
                    start_time=buffer.start_time or datetime.now(),
                )

        # Clear buffers
        self._audio_buffers.clear()

        if not payload:
            return

        logger.debug(
            "voice_actor.processing: users={}, sizes={}",
            len(payload),
            {uid: len(buf.pcm_bytes) for uid, buf in payload.items()},
        )

        try:
            events = await transcript_loop_once(
                payload,
                self.stt,
                self.sample_rate_hz,
                detector=self.detector,
                max_silence_ms=self.max_silence_ms,
                min_utterance_ms=self.min_utterance_ms,
            )

            # Sort by time and add to buffer
            sorted_events = sorted(events, key=lambda e: e.start_time)

            for event in sorted_events:
                if self._guild_id:
                    self._transcript_buffer.add(self._guild_id, event)

                if self._on_transcript:
                    await self._on_transcript(event)

                logger.info(
                    "voice_actor.transcript: speaker={}, text={}",
                    event.speaker_id,
                    event.text[:50] if event.text else "",
                )

        except Exception as e:
            logger.exception("voice_actor.process_error: {}", e)

    def _should_process(self) -> bool:
        """Check if buffers should be processed.

        Returns True if:
        - Any buffer exceeds the chunk size threshold, OR
        - Buffers have data AND no new audio for idle_timeout_seconds
        """
        if not self._audio_buffers:
            return False

        # Check chunk threshold
        bytes_per_sample = SDK_FORMAT.bytes_per_sample
        min_bytes = int(self.sample_rate_hz * self.chunk_seconds) * bytes_per_sample

        if any(len(buf.pcm_bytes) >= min_bytes for buf in self._audio_buffers.values()):
            return True

        # Check idle timeout
        if self._last_audio_time is not None:
            idle_seconds = (datetime.now() - self._last_audio_time).total_seconds()
            if idle_seconds >= self.idle_timeout_seconds:
                # Only if we have some data
                if any(buf.pcm_bytes for buf in self._audio_buffers.values()):
                    return True

        return False

    def _clear_state(self) -> None:
        """Clear all connection state."""
        self._status = VoiceStatus.DISCONNECTED
        self._guild_id = None
        self._channel_id = None
        self._voice_client = None
        self._audio_buffers.clear()
        self._last_audio_time = None
        self._reconnect_attempt = 0
        self._stale_posted = False
        logger.debug("voice_actor.state_cleared")

    # --- Timer Tasks ---

    async def _keepalive_timer(self) -> None:
        """Post SendKeepalive messages periodically."""
        try:
            while True:
                await asyncio.sleep(self.keepalive_interval)
                await self._inbox.put(SendKeepalive())
        except asyncio.CancelledError:
            pass

    async def _process_timer(self) -> None:
        """Post ProcessBuffers messages periodically."""
        try:
            while True:
                await asyncio.sleep(self.process_interval)
                await self._inbox.put(ProcessBuffers())
        except asyncio.CancelledError:
            pass

    async def _health_timer(self) -> None:
        """Check for stale audio and post StaleTimeout if needed."""
        try:
            while True:
                await asyncio.sleep(self.health_check_interval)

                if (
                    self._status == VoiceStatus.CONNECTED
                    and self._last_audio_time is not None
                    and not self._stale_posted
                ):
                    silence = (datetime.now() - self._last_audio_time).total_seconds()
                    if silence >= self.stale_threshold_seconds:
                        self._stale_posted = True
                        await self._inbox.put(StaleTimeout(silence_seconds=silence))
        except asyncio.CancelledError:
            pass


# --- Audio Sink ---


class VoiceActorSink(voice_recv.AudioSink):
    """Thin audio sink that posts to VoiceActor.

    Converts Discord stereo PCM to mono and posts AudioReceived messages.
    All processing happens in the actor — this is just a passthrough.
    """

    def __init__(self, actor: VoiceActor) -> None:
        super().__init__()
        self._actor = actor
        self._frame_count = 0

    def wants_opus(self) -> bool:
        """Request decoded PCM, not Opus."""
        return False

    def write(self, user: object, data: object) -> None:
        """Forward audio to actor.

        Called from voice_recv thread — uses actor.post_audio() which is
        thread-safe (Queue.put_nowait).
        """
        self._frame_count += 1

        if not user or not hasattr(user, "id"):
            return

        pcm_bytes = getattr(data, "pcm", None)
        if pcm_bytes is None:
            return

        # Log format info on first frame
        if self._frame_count == 1:
            expected_stereo = int(
                DISCORD_FORMAT.sample_rate_hz * 0.02 * DISCORD_FORMAT.bytes_per_sample
            )
            logger.info(
                "voice_actor_sink.first_frame: frame_bytes={}, expected_stereo={}",
                len(pcm_bytes),
                expected_stereo,
            )

        # Convert Discord stereo to mono
        try:
            mono_pcm = convert_pcm(pcm_bytes, DISCORD_FORMAT, SDK_FORMAT)
        except ValueError as e:
            if self._frame_count <= 5:
                logger.warning("voice_actor_sink.conversion_error: {}", e)
            return

        user_id = int(getattr(user, "id"))  # noqa: B009 - user is object type from voice_recv
        self._actor.post_audio(user_id, mono_pcm)

    def cleanup(self) -> None:
        """No-op — actor manages its own lifecycle."""
        pass
