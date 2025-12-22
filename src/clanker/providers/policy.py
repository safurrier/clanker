"""Policy protocol for request validation."""

from __future__ import annotations

from typing import Protocol

from ..models import Context


class Policy(Protocol):
    """Policy interface for validating contexts."""

    def validate(self, context: Context) -> None:
        """Validate context or raise an error."""
