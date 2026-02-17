"""Prompt utilities for Clanker."""

from __future__ import annotations

from collections.abc import Iterable

from .models import Message, Persona


def build_messages_with_persona(
    persona: Persona, messages: Iterable[Message]
) -> list[Message]:
    """Prepend persona system prompt to the message list."""
    system = Message(role="system", content=persona.system_prompt)
    return [system, *messages]
