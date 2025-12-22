"""Discord voice ingest wiring using voice_recv."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import discord
import discord.ext.voice_recv as voice_recv

from clanker.providers.base import STT
from clanker.voice.worker import transcript_loop_once


def voice_client_cls() -> type[discord.VoiceClient] | None:
    """Return the voice client class for voice receive, if available."""
    return voice_recv.VoiceRecvClient


@dataclass
class VoiceIngestWorker:
    """Buffers PCM frames and invokes STT pipeline."""

    stt: STT
    sample_rate_hz: int = 48000  # Discord voice uses 48kHz sample rate
    chunk_seconds: float = 2.0
    buffers: dict[int, bytearray] = field(default_factory=dict)

    def add_pcm(self, user_id: int, pcm_bytes: bytes) -> None:
        """Add PCM bytes for a user and trigger processing when large enough."""
        buffer = self.buffers.setdefault(user_id, bytearray())
        buffer.extend(pcm_bytes)

    async def process_once(self) -> list[str]:
        """Process current buffers once and return transcript texts."""
        if not self.buffers:
            return []
        payload = {user_id: bytes(buf) for user_id, buf in self.buffers.items()}
        self.buffers.clear()
        events = await transcript_loop_once(payload, self.stt, self.sample_rate_hz)
        return [event.text for event in events]

    def should_process(self) -> bool:
        """Check if any buffer exceeds the chunk size threshold."""
        min_bytes = int(self.sample_rate_hz * self.chunk_seconds) * 2
        return any(len(buffer) >= min_bytes for buffer in self.buffers.values())


class VoiceIngestSink(voice_recv.AudioSink):
    """voice_recv sink that forwards PCM frames to the worker."""

    def __init__(
        self,
        worker: VoiceIngestWorker,
        on_transcript: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self.worker = worker
        self.on_transcript = on_transcript
        self.logger = logging.getLogger(__name__)
        self._tasks: set[asyncio.Task] = set()

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
        texts = await self.worker.process_once()
        if not texts:
            return
        for text in texts:
            if self.on_transcript:
                await self.on_transcript(text)
            self.logger.info("voice_ingest.transcript", extra={"text": text})


async def start_voice_ingest(
    voice_client: voice_recv.VoiceRecvClient,
    stt: STT,
    on_transcript: Callable[[str], Awaitable[None]] | None = None,
) -> None:
    """Start voice ingest on a voice_recv-enabled voice client.

    Args:
        voice_client: A VoiceRecvClient instance with listen() support.
        stt: Speech-to-text provider.
        on_transcript: Optional callback for transcript events.
    """
    worker = VoiceIngestWorker(stt=stt)
    sink = VoiceIngestSink(worker, on_transcript=on_transcript)
    voice_client.listen(sink)
