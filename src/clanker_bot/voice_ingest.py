"""Discord voice ingest wiring using voice_recv."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import discord
import discord.ext.voice_recv as voice_recv
from loguru import logger

from clanker.providers.base import STT
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

    def get(self, guild_id: int) -> list[TranscriptEvent]:
        """Get recent transcript events for a guild."""
        self._prune(guild_id)
        return list(self._events.get(guild_id, []))

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
    """

    stt: STT
    sample_rate_hz: int = 48000  # Discord voice uses 48kHz sample rate
    chunk_seconds: float = 10.0  # Process every 10 seconds (was 2.0)
    max_silence_ms: int = 1000  # 1 second silence = new utterance (was 500ms)
    detector: SpeechDetector = field(default_factory=resolve_detector)
    buffers: dict[int, bytearray] = field(default_factory=dict)
    buffer_start_times: dict[int, datetime] = field(default_factory=dict)

    def add_pcm(
        self, user_id: int, pcm_bytes: bytes, recorded_at: datetime | None = None
    ) -> None:
        """Add PCM bytes for a user and trigger processing when large enough."""
        buffer = self.buffers.setdefault(user_id, bytearray())
        if not buffer:
            self.buffer_start_times[user_id] = recorded_at or datetime.now()
        buffer.extend(pcm_bytes)

    async def process_once(self) -> list[TranscriptEvent]:
        """Process current buffers once and return transcript events."""
        if not self.buffers:
            return []
        payload = {
            user_id: AudioBuffer(
                pcm_bytes=bytes(buf),
                start_time=self.buffer_start_times.get(user_id, datetime.now()),
            )
            for user_id, buf in self.buffers.items()
        }
        self.buffers.clear()
        self.buffer_start_times.clear()
        events = await transcript_loop_once(
            payload,
            self.stt,
            self.sample_rate_hz,
            detector=self.detector,
            max_silence_ms=self.max_silence_ms,
        )
        return sorted(events, key=lambda event: event.start_time)

    def should_process(self) -> bool:
        """Check if any buffer exceeds the chunk size threshold."""
        min_bytes = int(self.sample_rate_hz * self.chunk_seconds) * 2
        return any(len(buffer) >= min_bytes for buffer in self.buffers.values())


class VoiceIngestSink(voice_recv.AudioSink):
    """voice_recv sink that forwards PCM frames to the worker."""

    def __init__(
        self,
        worker: VoiceIngestWorker,
        on_transcript: Callable[[TranscriptEvent], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self.worker = worker
        self.on_transcript = on_transcript
        self._tasks: set[asyncio.Task[None]] = set()

    def wants_opus(self) -> bool:
        """Return False: we want decoded PCM, not Opus-encoded audio."""
        return False

    def cleanup(self) -> None:
        """Cancel pending processing tasks when sink is destroyed."""
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    def write(self, user: object, data: object) -> None:
        """Write audio data from a user (called by discord voice_recv)."""
        if not user or not hasattr(user, "id"):
            return
        if not hasattr(data, "pcm"):
            return
        self.worker.add_pcm(user.id, data.pcm)  # type: ignore[attr-defined]
        if self.worker.should_process():
            task = asyncio.create_task(self._flush())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _flush(self) -> None:
        events = await self.worker.process_once()
        if not events:
            return
        for event in events:
            if self.on_transcript:
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
) -> None:
    """Start voice ingest on a voice_recv-enabled voice client.

    Args:
        voice_client: A VoiceRecvClient instance with listen() support.
        stt: Speech-to-text provider.
        on_transcript: Optional callback for transcript events.
        detector: Optional speech detector override.
        chunk_seconds: Process buffer every N seconds (10s = conversations, 30s = meetings).
        max_silence_ms: Silence gap to split utterances (1000ms = natural pauses).
    """
    worker = VoiceIngestWorker(
        stt=stt,
        detector=detector or resolve_detector(),
        chunk_seconds=chunk_seconds,
        max_silence_ms=max_silence_ms,
    )
    sink = VoiceIngestSink(worker, on_transcript=on_transcript)
    voice_client.listen(sink)


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
