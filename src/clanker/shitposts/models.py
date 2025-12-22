"""Models for shitpost templates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ShitpostTemplate:
    """Template for a shitpost prompt."""

    name: str
    category: str
    prompt: str
    tags: Sequence[str]


@dataclass(frozen=True)
class ShitpostRequest:
    """Request for a shitpost generation."""

    template: ShitpostTemplate
    variables: Mapping[str, str]
