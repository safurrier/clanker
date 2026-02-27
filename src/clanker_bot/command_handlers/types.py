"""Shared types for command handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from clanker.models import Persona
from clanker.providers.base import LLM, STT, TTS, ImageGen

from ..discord_adapter import VoiceSessionManager
from ..metrics import Metrics

if TYPE_CHECKING:
    from clanker.providers.feedback import FeedbackStore

    from ..voice_actor import VoiceActor
    from ..voice_ingest import TranscriptBuffer


@dataclass(frozen=True)
class BotDependencies:
    """Dependencies for the bot commands."""

    llm: LLM
    stt: STT | None
    tts: TTS | None
    persona: Persona
    voice_manager: VoiceSessionManager
    image: ImageGen | None = None
    replay_log_path: Path | None = None
    metrics: Metrics | None = None
    voice_ingest_enabled: bool = True
    transcript_buffer: TranscriptBuffer | None = None
    feedback_store: FeedbackStore | None = None
    voice_actor: VoiceActor | None = None  # Actor-based voice (USE_VOICE_ACTOR=1)
