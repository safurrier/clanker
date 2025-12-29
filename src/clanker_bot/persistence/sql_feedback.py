"""FeedbackStore implementation using SQLite/PostgreSQL with sqlc-generated queries."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import sqlalchemy

from clanker.models import Interaction, Outcome
from clanker.providers.errors import PermanentProviderError, TransientProviderError

from .connection import close_pool, get_connection, get_engine, init_pool, is_sqlite
from .generated.interactions import (
    AsyncQuerier as InteractionsQuerier,
)
from .generated.interactions import (
    GetRecentInteractionsParams,
    GetUserStatsParams,
    RecordInteractionParams,
)

if TYPE_CHECKING:
    from .generated.models import Interaction as GeneratedInteraction


@dataclass
class SqlFeedbackStore:
    """SQLite/Postgres implementation of FeedbackStore.

    Uses sqlc-generated queries for type-safe database access.
    """

    _initialized: bool = field(default=False, init=False)

    async def initialize(self) -> None:
        """Initialize connection pool and run schema migrations."""
        if self._initialized:
            return

        await init_pool()

        # Run schema migrations using raw SQL
        schema_path = Path(__file__).parent / "db" / "schema.sql"
        schema = schema_path.read_text()

        engine = get_engine()
        async with engine.begin() as conn:
            if is_sqlite():
                # SQLite: execute each statement separately
                for statement in schema.split(";"):
                    statement = statement.strip()
                    if statement:
                        await conn.execute(sqlalchemy.text(statement))
            else:
                # PostgreSQL: execute as a single transaction
                await conn.execute(sqlalchemy.text(schema))

        self._initialized = True

    async def close(self) -> None:
        """Close connection pool."""
        await close_pool()
        self._initialized = False

    def _check_initialized(self) -> None:
        """Raise if store not initialized."""
        if not self._initialized:
            raise RuntimeError("Store not initialized. Call initialize() first.")

    async def record(self, interaction: Interaction) -> None:
        """Record a user interaction outcome."""
        self._check_initialized()

        async with get_connection() as conn:
            querier = InteractionsQuerier(conn)
            try:
                await querier.record_interaction(
                    RecordInteractionParams(
                        id=interaction.id,
                        guild_id=int(interaction.context_id),
                        user_id=int(interaction.user_id),
                        command=interaction.command,
                        outcome=interaction.outcome.value,
                        metadata=json.dumps(dict(interaction.metadata)),
                        created_at=interaction.created_at.isoformat(),
                    )
                )
            except Exception as e:
                error_str = str(e).lower()
                if "unique constraint" in error_str or "unique" in error_str:
                    raise PermanentProviderError(
                        f"Duplicate interaction ID: {interaction.id}"
                    ) from e
                raise TransientProviderError(
                    f"Failed to record interaction: {e}"
                ) from e

    async def get_user_stats(
        self,
        user_id: str,
        context_id: str | None = None,
        command: str | None = None,
    ) -> Mapping[Outcome, int]:
        """Get outcome counts for a user."""
        self._check_initialized()

        async with get_connection() as conn:
            querier = InteractionsQuerier(conn)
            params = GetUserStatsParams(
                user_id=int(user_id),
                column_2=int(context_id) if context_id else None,
                guild_id=int(context_id) if context_id else None,
                column_4=command,
                command=command,
            )

            # Initialize all outcomes to 0
            result: dict[Outcome, int] = dict.fromkeys(Outcome, 0)
            async for row in querier.get_user_stats(params):
                try:
                    outcome = Outcome(row.outcome)
                    result[outcome] = row.count
                except ValueError:
                    # Unknown outcome value, skip
                    pass

        return result

    async def get_recent_interactions(
        self,
        user_id: str,
        context_id: str | None = None,
        command: str | None = None,
        limit: int = 100,
    ) -> Sequence[Interaction]:
        """Get recent interactions in reverse chronological order."""
        self._check_initialized()

        async with get_connection() as conn:
            querier = InteractionsQuerier(conn)
            params = GetRecentInteractionsParams(
                user_id=int(user_id),
                column_2=int(context_id) if context_id else None,
                guild_id=int(context_id) if context_id else None,
                column_4=command,
                command=command,
                limit=limit,
            )

            results: list[Interaction] = []
            async for row in querier.get_recent_interactions(params):
                results.append(self._row_to_interaction(row))

        return results

    async def get_acceptance_rate(
        self,
        user_id: str,
        command: str,
        context_id: str | None = None,
    ) -> float:
        """Calculate acceptance rate for a user/command."""
        self._check_initialized()

        async with get_connection() as conn:
            querier = InteractionsQuerier(conn)
            rate = await querier.get_acceptance_rate(
                user_id=int(user_id),
                command=command,
                dollar_3=int(context_id) if context_id else None,
                guild_id=int(context_id) if context_id else None,
            )

        if rate is None:
            return 0.5
        return float(rate)

    def _row_to_interaction(self, row: GeneratedInteraction) -> Interaction:
        """Convert a generated model to the SDK Interaction model."""
        metadata_str = row.metadata
        metadata = json.loads(metadata_str) if metadata_str else {}

        return Interaction(
            id=row.id,
            context_id=str(row.guild_id),
            user_id=str(row.user_id),
            command=row.command,
            outcome=Outcome(row.outcome),
            metadata=metadata,
            created_at=datetime.fromisoformat(row.created_at),
        )
