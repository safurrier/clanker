"""Discord voice ingest wiring using voice_recv."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import discord
import discord.ext.voice_recv as voice_recv
from loguru import logger

from clanker.providers.audio_utils import convert_pcm
from clanker.providers.base import STT
from clanker.voice.debug import DebugCapture, DebugConfig
from clanker.voice.formats import DISCORD_FORMAT, SDK_FORMAT
from clanker.voice.vad import EnergyVAD, SileroVAD, SpeechDetector, resolve_detector
from clanker.voice.worker import AudioBuffer, TranscriptEvent, transcript_loop_once


@dataclass
class TranscriptBuffer:
    """Maintains a rolling buffer of recent transcript events per guild.

    Used by shitpost command to get voice context.

    Note: Currently keyed by guild_id only (not channel_id) since the bot
    supports one voice connection per guild. If we expand to multiple
    simultaneous voice sessions per guild, this will need channel_id keying
    to avoid mixing transcripts between sessions.
    """

    max_events: int = 50
    max_age_minutes: float = 5.0
    _events: dict[int, list[TranscriptEvent]] = field(default_factory=dict)

    def add(self, guild_id: int, event: TranscriptEvent) -> None:
        """Add a transcript event for a guild."""
        if guild_id not in self._events:
            self._events[guild_id] = []
        self._events[guild_id].append(event)
        self._prune(guild_id)
        logger.debug(
            "transcript_buffer.add: guild={}, speaker={}, total_events={}",
            guild_id,
            event.speaker_id,
            len(self._events[guild_id]),
        )

    def get(self, guild_id: int) -> list[TranscriptEvent]:
        """Get recent transcript events for a guild."""
        self._prune(guild_id)
        events = list(self._events.get(guild_id, []))
        logger.debug(
            "transcript_buffer.get: guild={}, event_count={}",
            guild_id,
            len(events),
        )
        return events

    def clear(self, guild_id: int) -> None:
        """Clear transcript buffer for a guild."""
        self._events.pop(guild_id, None)

    def has_events(self, guild_id: int) -> bool:
        """Check if there are any recent events for a guild."""
        return bool(self.get(guild_id))

    def _prune(self, guild_id: int) -> None:
        """Remove old events and enforce max count."""
        events = self._events.get(guild_id, [])
        if not events:
            return

        cutoff = datetime.now() - timedelta(minutes=self.max_age_minutes)
        events = [e for e in events if e.start_time >= cutoff]

        # Enforce max_events limit
        if len(events) > self.max_events:
            events = events[-self.max_events :]

        self._events[guild_id] = events


def voice_client_cls() -> type[discord.VoiceClient] | None:
    """Return the voice client class for voice receive, if available."""
    return voice_recv.VoiceRecvClient


@dataclass
class VoiceIngestWorker:
    """Buffers PCM frames and invokes STT pipeline.

    Args:
        stt: Speech-to-text provider
        sample_rate_hz: Audio sample rate (Discord uses 48kHz)
        chunk_seconds: Buffer threshold - process every N seconds
                      (10s = good for conversations, 30s = meetings/monologues)
        max_silence_ms: Silence gap to split utterances
                       (1000ms = natural pauses in speech)
        detector: Voice activity detector (SileroVAD or EnergyVAD)
        debug_capture: Optional debug capture instance (enable via VOICE_DEBUG=1)
    """

    stt: STT
    sample_rate_hz: int = 48000  # Discord voice uses 48kHz sample rate
    chunk_seconds: float = 10.0  # Process every 10 seconds (was 2.0)
    max_silence_ms: int = 1000  # 1 second silence = new utterance (was 500ms)
    min_utterance_ms: int = 500  # Minimum utterance duration
    detector: SpeechDetector = field(default_factory=resolve_detector)
    debug_capture: DebugCapture | None = field(default=None)
    buffers: dict[int, bytearray] = field(default_factory=dict)
    buffer_start_times: dict[int, datetime] = field(default_factory=dict)

    def add_pcm(
        self, user_id: int, pcm_bytes: bytes, recorded_at: datetime | None = None
    ) -> None:
        """Add PCM bytes for a user and trigger processing when large enough."""
        buffer = self.buffers.setdefault(user_id, bytearray())
        if not buffer:
            self.buffer_start_times[user_id] = recorded_at or datetime.now()
            logger.debug("voice_worker.new_buffer: user={}", user_id)
        buffer.extend(pcm_bytes)

    async def process_once(self) -> list[TranscriptEvent]:
        """Process current buffers once and return transcript events."""
        if not self.buffers:
            return []

        buffer_sizes = {uid: len(buf) for uid, buf in self.buffers.items()}
        logger.debug(
            "voice_worker.process_start: buffers={}, sizes={}",
            len(self.buffers),
            buffer_sizes,
        )

        payload = {
            user_id: AudioBuffer(
                pcm_bytes=bytes(buf),
                start_time=self.buffer_start_times.get(user_id, datetime.now()),
            )
            for user_id, buf in self.buffers.items()
        }
        self.buffers.clear()
        self.buffer_start_times.clear()

        # Start debug session if enabled
        if self.debug_capture and self.debug_capture.enabled:
            vad_type = type(self.detector).__name__.lower().replace("vad", "")
            config = DebugConfig(
                sample_rate_hz=self.sample_rate_hz,
                chunk_seconds=self.chunk_seconds,
                max_silence_ms=self.max_silence_ms,
                min_utterance_ms=self.min_utterance_ms,
                vad_type=vad_type,
            )
            self.debug_capture.start_session(config)

        events = await transcript_loop_once(
            payload,
            self.stt,
            self.sample_rate_hz,
            detector=self.detector,
            max_silence_ms=self.max_silence_ms,
            min_utterance_ms=self.min_utterance_ms,
            debug_capture=self.debug_capture,
        )

        # End debug session
        if self.debug_capture and self.debug_capture.enabled:
            self.debug_capture.end_session()

        sorted_events = sorted(events, key=lambda event: event.start_time)
        logger.debug(
            "voice_worker.process_complete: events={}",
            len(sorted_events),
        )
        return sorted_events

    def should_process(self) -> bool:
        """Check if any buffer exceeds the chunk size threshold."""
        # SDK_FORMAT.bytes_per_sample = 2 for mono 16-bit
        bytes_per_sample = SDK_FORMAT.bytes_per_sample
        min_bytes = int(self.sample_rate_hz * self.chunk_seconds) * bytes_per_sample
        should = any(len(buffer) >= min_bytes for buffer in self.buffers.values())
        if should:
            sizes = {uid: len(buf) for uid, buf in self.buffers.items()}
            logger.debug(
                "voice_worker.threshold_reached: min_bytes={}, sizes={}",
                min_bytes,
                sizes,
            )
        return should


class VoiceIngestSink(voice_recv.AudioSink):
    """voice_recv sink that forwards PCM frames to the worker.

    Uses a background async task for processing instead of thread/async bridging.
    The write() method (called from voice_recv's thread) just buffers data.
    Processing happens in the async world via a periodic task.
    """

    def __init__(
        self,
        worker: VoiceIngestWorker,
        on_transcript: Callable[[TranscriptEvent], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self.worker = worker
        self.on_transcript = on_transcript
        self._frame_count: int = 0
        self._total_bytes: int = 0
        self._process_task: asyncio.Task[None] | None = None
        self._stopped = False
        logger.debug("voice_sink.created: callback={}", on_transcript is not None)

    def wants_opus(self) -> bool:
        """Return False: we want decoded PCM, not Opus-encoded audio."""
        return False

    def start_processing(self) -> None:
        """Start the background processing task."""
        if self._process_task is not None:
            return
        self._stopped = False
        self._process_task = asyncio.create_task(self._process_loop())
        logger.debug("voice_sink.processing_started")

    def stop_processing(self) -> None:
        """Stop the background processing task."""
        self._stopped = True
        if self._process_task is not None:
            self._process_task.cancel()
            self._process_task = None
        logger.debug("voice_sink.processing_stopped")

    def cleanup(self) -> None:
        """Cancel processing task when sink is destroyed."""
        self.stop_processing()

    def write(self, user: object, data: object) -> None:
        """Write audio data from a user (called from voice_recv thread).

        This method just buffers data - no async operations.
        Processing happens in _process_loop().

        Discord delivers stereo 48kHz PCM. We convert to mono here at the
        boundary before passing to the SDK pipeline.
        """
        self._frame_count += 1

        pcm_bytes = getattr(data, "pcm", None)

        # Log format info on first frame for debugging
        if self._frame_count == 1:
            if pcm_bytes:
                # Discord 20ms frame @ 48kHz stereo = 3840 bytes
                expected_stereo = int(
                    DISCORD_FORMAT.sample_rate_hz
                    * 0.02
                    * DISCORD_FORMAT.bytes_per_sample
                )
                logger.info(
                    "voice_sink.format_check: frame_bytes={}, expected_stereo={}, "
                    "ratio={:.2f}",
                    len(pcm_bytes),
                    expected_stereo,
                    len(pcm_bytes) / expected_stereo if expected_stereo else 0,
                )
            logger.debug(
                "voice_sink.first_frame: user_type={}, data_type={}",
                type(user).__name__,
                type(data).__name__,
            )

        if not user or not hasattr(user, "id"):
            if self._frame_count <= 5:
                logger.debug(
                    "voice_sink.skip_frame: no_user={}, no_id={}",
                    not user,
                    not hasattr(user, "id") if user else "N/A",
                )
            return

        if pcm_bytes is None:
            if self._frame_count <= 5:
                logger.debug("voice_sink.skip_frame: no_pcm_attr")
            return

        # Convert Discord stereo to SDK mono format
        try:
            mono_pcm = convert_pcm(pcm_bytes, DISCORD_FORMAT, SDK_FORMAT)
        except ValueError as e:
            if self._frame_count <= 5:
                logger.warning("voice_sink.conversion_error: {}", e)
            return

        user_id = int(getattr(user, "id"))  # noqa: B009 - user is object type from voice_recv
        self._total_bytes += len(mono_pcm)
        self.worker.add_pcm(user_id, mono_pcm)

        # Log progress every 500 frames (~10 seconds at 50fps)
        if self._frame_count % 500 == 0:
            logger.debug(
                "voice_sink.progress: frames={}, total_bytes={}, buffers={}",
                self._frame_count,
                self._total_bytes,
                len(self.worker.buffers),
            )

    async def _process_loop(self) -> None:
        """Background task that periodically processes buffered audio."""
        logger.debug("voice_sink.process_loop_started")
        while not self._stopped:
            try:
                await asyncio.sleep(1.0)  # Check every second
                if self.worker.should_process():
                    await self._flush()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("voice_sink.process_loop_error")
        logger.debug("voice_sink.process_loop_stopped")

    async def _flush(self) -> None:
        """Process buffered audio and invoke callbacks."""
        logger.debug("voice_sink.flush_start")
        events = await self.worker.process_once()
        logger.debug(
            "voice_sink.flush_complete: events={}, callback={}",
            len(events),
            self.on_transcript is not None,
        )
        if not events:
            return
        for event in events:
            if self.on_transcript:
                logger.debug(
                    "voice_sink.invoking_callback: speaker={}, text_len={}",
                    event.speaker_id,
                    len(event.text) if event.text else 0,
                )
                await self.on_transcript(event)
            logger.info(
                "voice_ingest.transcript",
                text=event.text,
                speaker_id=event.speaker_id,
                start_time=event.start_time.isoformat(),
                end_time=event.end_time.isoformat(),
            )


async def start_voice_ingest(
    voice_client: voice_recv.VoiceRecvClient,
    stt: STT,
    on_transcript: Callable[[TranscriptEvent], Awaitable[None]] | None = None,
    detector: SpeechDetector | None = None,
    chunk_seconds: float = 10.0,
    max_silence_ms: int = 1000,
    debug_capture: DebugCapture | None = None,
) -> VoiceIngestSink:
    """Start voice ingest on a voice_recv-enabled voice client.

    Args:
        voice_client: A VoiceRecvClient instance with listen() support.
        stt: Speech-to-text provider.
        on_transcript: Optional callback for transcript events.
        detector: Optional speech detector override.
        chunk_seconds: Process buffer every N seconds (10s = conversations, 30s = meetings).
        max_silence_ms: Silence gap to split utterances (1000ms = natural pauses).
        debug_capture: Optional debug capture instance. If None and VOICE_DEBUG=1 is set,
            a DebugCapture will be created automatically.

    Returns:
        The VoiceIngestSink instance (call stop_processing() on cleanup).
    """
    # Create debug capture from env if not provided
    if debug_capture is None:
        debug_capture = DebugCapture.from_env()

    logger.debug(
        "start_voice_ingest: client_type={}, stt={}, callback={}, debug={}",
        type(voice_client).__name__,
        type(stt).__name__,
        on_transcript is not None,
        debug_capture.enabled if debug_capture else False,
    )
    worker = VoiceIngestWorker(
        stt=stt,
        detector=detector or resolve_detector(),
        chunk_seconds=chunk_seconds,
        max_silence_ms=max_silence_ms,
        debug_capture=debug_capture,
    )
    sink = VoiceIngestSink(worker, on_transcript=on_transcript)
    voice_client.listen(sink)
    sink.start_processing()
    logger.debug("start_voice_ingest: listen() and processing started")
    return sink


async def warmup_voice_detector(prefer_silero: bool = True) -> SpeechDetector:
    """Warmup and return the best available speech detector.

    This should be called on bot startup to pre-load the Silero VAD model
    and validate that dependencies are available.

    Args:
        prefer_silero: Whether to prefer Silero VAD over EnergyVAD.

    Returns:
        A warmed-up SpeechDetector (SileroVAD or EnergyVAD fallback).
    """
    if not prefer_silero:
        logger.info("Using EnergyVAD (Silero disabled by config)")
        return EnergyVAD()

    try:
        logger.info("Warming up Silero VAD...")
        detector = SileroVAD(warmup=True)

        # Test with dummy audio to ensure model is loaded
        dummy_pcm = b"\x00\x00" * 16000  # 1 second of silence at 16kHz
        detector.detect(dummy_pcm, 16000)

        logger.info("Silero VAD ready")
        return detector

    except Exception as e:
        logger.warning(f"Silero VAD unavailable, falling back to EnergyVAD: {e}")
        return EnergyVAD()
