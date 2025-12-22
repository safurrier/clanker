"""Domain models for Clanker."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

from .constants import SCHEMA_VERSION


@dataclass(frozen=True)
class Message:
    """Represents a chat message."""

    role: str
    content: str


@dataclass(frozen=True)
class Persona:
    """Persona data for prompt injection and voice settings."""

    id: str
    display_name: str
    system_prompt: str
    tts_voice: str | None = None
    providers: Mapping[str, str] | None = None


@dataclass(frozen=True)
class Context:
    """Immutable request context for Clanker."""

    request_id: str
    user_id: int
    guild_id: int | None
    channel_id: int
    persona: Persona
    messages: Sequence[Message]
    metadata: Mapping[str, str]

    def to_dict(self) -> dict:
        """Serialize context to a schema-versioned dictionary."""
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "persona": {
                "id": self.persona.id,
                "display_name": self.persona.display_name,
                "system_prompt": self.persona.system_prompt,
                "tts_voice": self.persona.tts_voice,
                "providers": dict(self.persona.providers or {}),
            },
            "messages": [
                {"role": message.role, "content": message.content}
                for message in self.messages
            ],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Context:
        """Deserialize a context from a schema-versioned dictionary."""
        schema_version = payload.get("schema_version")
        if schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported schema version")

        persona_payload = cast(Mapping[str, object], payload["persona"])
        persona = Persona(
            id=str(persona_payload["id"]),
            display_name=str(persona_payload["display_name"]),
            system_prompt=str(persona_payload["system_prompt"]),
            tts_voice=cast(str | None, persona_payload.get("tts_voice")),
            providers=cast(Mapping[str, str], persona_payload.get("providers") or {}),
        )
        messages_payload = cast(Sequence[Mapping[str, object]], payload["messages"])
        messages = [
            Message(role=str(item["role"]), content=str(item["content"]))
            for item in messages_payload
        ]
        metadata = cast(Mapping[str, object], payload.get("metadata") or {})
        guild_raw = payload.get("guild_id")
        guild_id = int(cast(int | str, guild_raw)) if guild_raw is not None else None
        return cls(
            request_id=str(payload["request_id"]),
            user_id=int(cast(int | str, payload["user_id"])),
            guild_id=guild_id,
            channel_id=int(cast(int | str, payload["channel_id"])),
            persona=persona,
            messages=messages,
            metadata={str(key): str(value) for key, value in metadata.items()},
        )


@dataclass(frozen=True)
class ReplayEntry:
    """Entry for persisted replay logs."""

    timestamp: str
    context: dict
    response: dict
    has_audio: bool

    @classmethod
    def create(cls, context: Context, reply: Message, has_audio: bool) -> ReplayEntry:
        """Create a replay entry from context and reply."""
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            context=context.to_dict(),
            response={"role": reply.role, "content": reply.content},
            has_audio=has_audio,
        )
