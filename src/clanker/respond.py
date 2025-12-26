"""Use-case logic for responding to contexts."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path

from loguru import logger

from .constants import REPLAY_LOG_FILENAME
from .models import Context, Message, ReplayEntry
from .providers.base import LLM, TTS


async def respond(
    context: Context,
    llm: LLM,
    tts: TTS | None = None,
    replay_log_path: Path | None = None,
) -> tuple[Message, bytes | None]:
    """Generate a response for the given context."""
    _log_context(context)
    reply = await llm.generate(context, list(context.messages))

    audio: bytes | None = None
    if tts is not None and context.persona.tts_voice:
        audio = await tts.synthesize(reply.content, context.persona.tts_voice)

    log_path = replay_log_path or Path(REPLAY_LOG_FILENAME)
    log_task = asyncio.create_task(
        _persist_replay_entry(log_path, context, reply, audio)
    )
    log_task.add_done_callback(_log_task_errors)

    return reply, audio


def _log_task_errors(task: asyncio.Task) -> None:
    """Log exceptions from background tasks."""
    try:
        task.result()
    except Exception:
        logger.exception("Error in background replay logging task")


async def _persist_replay_entry(
    log_path: Path,
    context: Context,
    reply: Message,
    audio: bytes | None,
) -> None:
    """Persist a replay log entry asynchronously."""
    entry = ReplayEntry.create(context, reply, audio is not None)
    payload = _serialize_json(entry)
    await asyncio.to_thread(_append_line, log_path, payload)


def _append_line(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.write("\n")


def _serialize_json(entry: ReplayEntry) -> str:
    import json

    return json.dumps(
        {
            "timestamp": entry.timestamp,
            "context": entry.context,
            "response": entry.response,
            "has_audio": entry.has_audio,
        },
        ensure_ascii=False,
    )


def combine_messages(messages: Iterable[Message]) -> str:
    """Combine messages into a simple transcript string."""
    return "\n".join(f"{message.role}: {message.content}" for message in messages)


def _log_context(context: Context) -> None:
    logger.info(
        "clanker.respond",
        request_id=context.request_id,
        persona_id=context.persona.id,
        message_count=len(context.messages),
    )
