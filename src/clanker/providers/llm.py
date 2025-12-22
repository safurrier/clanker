"""LLM provider protocol."""

from __future__ import annotations

from typing import Protocol

from ..models import Context, Message


class LLM(Protocol):
    """Large language model interface."""

    async def generate(
        self, context: Context, messages: list[Message], params: dict | None = None
    ) -> Message:
        """Generate a reply message."""
