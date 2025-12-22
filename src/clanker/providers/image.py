"""Image generation provider protocol."""

from __future__ import annotations

from typing import Protocol


class ImageGen(Protocol):
    """Image generation interface."""

    async def generate(self, spec: dict) -> bytes | str:
        """Generate an image payload from a spec."""
