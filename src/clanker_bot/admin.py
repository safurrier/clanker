"""Admin state for Clanker bot."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AdminState:
    """Tracks admin-configurable state."""

    allow_new_meetings: bool = True
