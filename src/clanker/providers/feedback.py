"""Protocol for feedback storage."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..models import Interaction, Outcome


class FeedbackStore(Protocol):
    """Protocol for storing and retrieving interaction feedback.

    Implementations should handle storage of user interaction outcomes
    (accept/reject/regenerate) for feedback loops and analytics.
    """

    async def record(self, interaction: Interaction) -> None:
        """Record a user interaction outcome.

        Args:
            interaction: The interaction to store

        Raises:
            TransientProviderError: Temporary storage failure (retry)
            PermanentProviderError: Unrecoverable failure (e.g., duplicate ID)
        """
        ...

    async def get_user_stats(
        self,
        user_id: str,
        context_id: str | None = None,
        command: str | None = None,
    ) -> Mapping[Outcome, int]:
        """Get outcome counts for a user.

        Args:
            user_id: User to query
            context_id: Optional guild/context filter
            command: Optional command filter

        Returns:
            Mapping of outcome -> count
        """
        ...

    async def get_recent_interactions(
        self,
        user_id: str,
        context_id: str | None = None,
        command: str | None = None,
        limit: int = 100,
    ) -> Sequence[Interaction]:
        """Get recent interactions for analysis.

        Args:
            user_id: User to query
            context_id: Optional guild/context filter
            command: Optional command filter
            limit: Max interactions to return

        Returns:
            Interactions in reverse chronological order
        """
        ...

    async def get_acceptance_rate(
        self,
        user_id: str,
        command: str,
        context_id: str | None = None,
    ) -> float:
        """Calculate acceptance rate for a user/command.

        Acceptance rate = accepted / (accepted + rejected + regenerated)
        Timeout outcomes are excluded from the calculation.

        Args:
            user_id: User to query
            command: Command to filter by
            context_id: Optional guild/context filter

        Returns:
            Float 0.0-1.0, or 0.5 if no data
        """
        ...
