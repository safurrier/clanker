"""Simple in-memory metrics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Metrics:
    """In-memory counters for bot activity."""

    counters: Counter[str] = field(default_factory=Counter)

    def increment(self, key: str) -> None:
        self.counters[key] += 1

    def snapshot(self) -> dict[str, int]:
        return dict(self.counters)
