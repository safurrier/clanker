"""Tests for SqlFeedbackStore with SQLite backend."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy

from clanker.models import Interaction, Outcome
from clanker.providers.errors import PermanentProviderError
from clanker_bot.persistence import SqlFeedbackStore


def make_interaction(
    *,
    id: str | None = None,
    user_id: str = "123456789",
    context_id: str = "987654321",
    command: str = "shitpost",
    outcome: Outcome = Outcome.ACCEPTED,
    metadata: dict | None = None,
    created_at: datetime | None = None,
) -> Interaction:
    """Create a test interaction with sensible defaults."""
    return Interaction(
        id=id or str(uuid.uuid4()),
        user_id=user_id,
        context_id=context_id,
        command=command,
        outcome=outcome,
        metadata=metadata or {},
        created_at=created_at or datetime.now(timezone.utc),
    )


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """Create a temporary database path for testing."""
    return str(tmp_path / "test.db")


@pytest.fixture
def db_env(temp_db_path: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Set up DATABASE_URL environment variable for testing."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{temp_db_path}")
    return temp_db_path


@pytest.fixture
async def store(db_env: str) -> SqlFeedbackStore:
    """Create and initialize a SqlFeedbackStore for testing."""
    store = SqlFeedbackStore()
    await store.initialize()
    yield store
    await store.close()


class TestSqlFeedbackStoreInitialization:
    """Tests for SqlFeedbackStore initialization."""

    @pytest.mark.asyncio
    async def test_initialize_creates_database(
        self, temp_db_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Database file is created on initialize."""
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{temp_db_path}")
        assert not Path(temp_db_path).exists()

        store = SqlFeedbackStore()
        await store.initialize()

        assert Path(temp_db_path).exists()
        await store.close()

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, store: SqlFeedbackStore) -> None:
        """Schema creates expected tables."""
        from clanker_bot.persistence.connection import get_connection

        async with get_connection() as conn:
            result = await conn.execute(
                sqlalchemy.text(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            )
            tables = {row[0] for row in result.fetchall()}

        assert "interactions" in tables
        assert "user_preferences" in tables
        assert "guild_config" in tables

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self, store: SqlFeedbackStore) -> None:
        """Calling initialize multiple times is safe."""
        # Record some data
        await store.record(make_interaction())

        # Re-initialize
        await store.initialize()

        # Data should still exist
        stats = await store.get_user_stats("123456789")
        assert stats[Outcome.ACCEPTED] == 1

    @pytest.mark.asyncio
    async def test_operations_before_initialize_raise(
        self, temp_db_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Operations before initialize raise RuntimeError."""
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{temp_db_path}")
        store = SqlFeedbackStore()

        with pytest.raises(RuntimeError, match="not initialized"):
            await store.record(make_interaction())


class TestSqlFeedbackStoreRecord:
    """Tests for SqlFeedbackStore.record()."""

    @pytest.mark.asyncio
    async def test_record_inserts_row(self, store: SqlFeedbackStore) -> None:
        """Recording an interaction inserts a database row."""
        interaction = make_interaction(id="test-123")

        await store.record(interaction)

        from clanker_bot.persistence.connection import get_connection

        async with get_connection() as conn:
            result = await conn.execute(
                sqlalchemy.text("SELECT * FROM interactions WHERE id = :id"),
                {"id": "test-123"},
            )
            row = result.fetchone()

        assert row is not None
        assert row[0] == "test-123"  # id
        assert row[4] == "accepted"  # outcome

    @pytest.mark.asyncio
    async def test_record_with_metadata(self, store: SqlFeedbackStore) -> None:
        """Metadata is JSON-serialized correctly."""
        interaction = make_interaction(
            id="test-meta",
            metadata={"template": "drake", "length": 42},
        )

        await store.record(interaction)

        from clanker_bot.persistence.connection import get_connection

        async with get_connection() as conn:
            result = await conn.execute(
                sqlalchemy.text("SELECT metadata FROM interactions WHERE id = :id"),
                {"id": "test-meta"},
            )
            row = result.fetchone()

        metadata = json.loads(row[0])
        assert metadata["template"] == "drake"
        assert metadata["length"] == 42

    @pytest.mark.asyncio
    async def test_record_duplicate_raises(self, store: SqlFeedbackStore) -> None:
        """Recording duplicate interaction ID raises PermanentProviderError."""
        interaction = make_interaction(id="duplicate-123")

        await store.record(interaction)

        with pytest.raises(PermanentProviderError, match="Duplicate"):
            await store.record(interaction)


class TestSqlFeedbackStoreUserStats:
    """Tests for SqlFeedbackStore.get_user_stats()."""

    @pytest.mark.asyncio
    async def test_user_stats_empty(self, store: SqlFeedbackStore) -> None:
        """Empty store returns zero counts for all outcomes."""
        stats = await store.get_user_stats("999999999")  # Non-existent user

        assert stats[Outcome.ACCEPTED] == 0
        assert stats[Outcome.REJECTED] == 0
        assert stats[Outcome.REGENERATED] == 0
        assert stats[Outcome.TIMEOUT] == 0

    @pytest.mark.asyncio
    async def test_user_stats_aggregates_correctly(
        self, store: SqlFeedbackStore
    ) -> None:
        """User stats aggregates outcomes correctly."""
        # Record mixed outcomes
        for outcome, count in [
            (Outcome.ACCEPTED, 5),
            (Outcome.REJECTED, 2),
            (Outcome.REGENERATED, 3),
        ]:
            for _ in range(count):
                await store.record(make_interaction(outcome=outcome))

        stats = await store.get_user_stats("123456789")

        assert stats[Outcome.ACCEPTED] == 5
        assert stats[Outcome.REJECTED] == 2
        assert stats[Outcome.REGENERATED] == 3

    @pytest.mark.asyncio
    async def test_user_stats_filters_by_context(self, store: SqlFeedbackStore) -> None:
        """User stats can be filtered by context_id."""
        # Guild A: 3 accepted
        for _ in range(3):
            await store.record(
                make_interaction(context_id="111", outcome=Outcome.ACCEPTED)
            )
        # Guild B: 2 accepted
        for _ in range(2):
            await store.record(
                make_interaction(context_id="222", outcome=Outcome.ACCEPTED)
            )

        stats_a = await store.get_user_stats("123456789", context_id="111")
        stats_b = await store.get_user_stats("123456789", context_id="222")
        stats_all = await store.get_user_stats("123456789")

        assert stats_a[Outcome.ACCEPTED] == 3
        assert stats_b[Outcome.ACCEPTED] == 2
        assert stats_all[Outcome.ACCEPTED] == 5

    @pytest.mark.asyncio
    async def test_user_stats_filters_by_command(self, store: SqlFeedbackStore) -> None:
        """User stats can be filtered by command."""
        await store.record(
            make_interaction(command="shitpost", outcome=Outcome.ACCEPTED)
        )
        await store.record(
            make_interaction(command="shitpost", outcome=Outcome.ACCEPTED)
        )
        await store.record(make_interaction(command="chat", outcome=Outcome.ACCEPTED))

        stats_shitpost = await store.get_user_stats("123456789", command="shitpost")
        stats_chat = await store.get_user_stats("123456789", command="chat")

        assert stats_shitpost[Outcome.ACCEPTED] == 2
        assert stats_chat[Outcome.ACCEPTED] == 1


class TestSqlFeedbackStoreRecentInteractions:
    """Tests for SqlFeedbackStore.get_recent_interactions()."""

    @pytest.mark.asyncio
    async def test_recent_interactions_empty(self, store: SqlFeedbackStore) -> None:
        """Empty store returns empty list."""
        recent = await store.get_recent_interactions("999999999")  # Non-existent user
        assert recent == []

    @pytest.mark.asyncio
    async def test_recent_interactions_respects_limit(
        self, store: SqlFeedbackStore
    ) -> None:
        """Returns at most limit interactions."""
        for i in range(10):
            await store.record(make_interaction(id=f"interaction-{i}"))

        recent = await store.get_recent_interactions("123456789", limit=5)

        assert len(recent) == 5

    @pytest.mark.asyncio
    async def test_recent_interactions_ordered_by_time(
        self, store: SqlFeedbackStore
    ) -> None:
        """Returns interactions in reverse chronological order."""
        now = datetime.now(timezone.utc)

        # Record interactions with different timestamps (oldest first)
        for i in range(5):
            await store.record(
                make_interaction(
                    id=f"interaction-{i}",
                    created_at=now - timedelta(minutes=4 - i),  # 0 is oldest
                )
            )

        recent = await store.get_recent_interactions("123456789")

        # Most recent (i=4) should be first
        assert recent[0].id == "interaction-4"
        assert recent[4].id == "interaction-0"

    @pytest.mark.asyncio
    async def test_recent_interactions_roundtrip(self, store: SqlFeedbackStore) -> None:
        """Interaction data survives roundtrip through database."""
        now = datetime.now(timezone.utc)
        original = make_interaction(
            id="roundtrip-test",
            user_id="111",
            context_id="222",
            command="shitpost",
            outcome=Outcome.REGENERATED,
            metadata={"template": "drake", "score": 0.95},
            created_at=now,
        )

        await store.record(original)
        recent = await store.get_recent_interactions("111")

        assert len(recent) == 1
        retrieved = recent[0]
        assert retrieved.id == original.id
        assert retrieved.user_id == original.user_id
        assert retrieved.context_id == original.context_id
        assert retrieved.command == original.command
        assert retrieved.outcome == original.outcome
        assert retrieved.metadata == dict(original.metadata)


class TestSqlFeedbackStoreAcceptanceRate:
    """Tests for SqlFeedbackStore.get_acceptance_rate()."""

    @pytest.mark.asyncio
    async def test_acceptance_rate_no_data(self, store: SqlFeedbackStore) -> None:
        """Returns 0.5 when no data exists."""
        rate = await store.get_acceptance_rate(
            "999999999", "shitpost"
        )  # Non-existent user
        assert rate == 0.5

    @pytest.mark.asyncio
    async def test_acceptance_rate_all_accepted(self, store: SqlFeedbackStore) -> None:
        """Returns 1.0 when all interactions are accepted."""
        for _ in range(5):
            await store.record(make_interaction(outcome=Outcome.ACCEPTED))

        rate = await store.get_acceptance_rate("123456789", "shitpost")
        assert rate == 1.0

    @pytest.mark.asyncio
    async def test_acceptance_rate_none_accepted(self, store: SqlFeedbackStore) -> None:
        """Returns 0.0 when no interactions are accepted."""
        for _ in range(3):
            await store.record(make_interaction(outcome=Outcome.REJECTED))

        rate = await store.get_acceptance_rate("123456789", "shitpost")
        assert rate == 0.0

    @pytest.mark.asyncio
    async def test_acceptance_rate_mixed(self, store: SqlFeedbackStore) -> None:
        """Calculates correct rate for mixed outcomes."""
        # 3 accepted, 1 rejected = 75%
        for _ in range(3):
            await store.record(make_interaction(outcome=Outcome.ACCEPTED))
        await store.record(make_interaction(outcome=Outcome.REJECTED))

        rate = await store.get_acceptance_rate("123456789", "shitpost")
        assert rate == 0.75

    @pytest.mark.asyncio
    async def test_acceptance_rate_excludes_timeout(
        self, store: SqlFeedbackStore
    ) -> None:
        """Timeout outcomes are excluded from rate calculation."""
        # 2 accepted, 1 rejected, 5 timeout = 2/3 = 66.7%
        await store.record(make_interaction(outcome=Outcome.ACCEPTED))
        await store.record(make_interaction(outcome=Outcome.ACCEPTED))
        await store.record(make_interaction(outcome=Outcome.REJECTED))
        for _ in range(5):
            await store.record(make_interaction(outcome=Outcome.TIMEOUT))

        rate = await store.get_acceptance_rate("123456789", "shitpost")
        assert abs(rate - 0.667) < 0.01


class TestSchemaCompatibility:
    """Tests for schema compatibility across database backends."""

    def test_schema_splits_into_valid_statements(self) -> None:
        """Verify schema.sql can be split for asyncpg compatibility.

        asyncpg doesn't support multi-statement execution, so we split on ';'.
        This test ensures the schema file remains splittable without issues.
        """
        schema_path = (
            Path(__file__).parent.parent
            / "src/clanker_bot/persistence/db/schema.sql"
        )
        schema = schema_path.read_text()

        statements = [s.strip() for s in schema.split(";") if s.strip()]

        # Should have multiple statements (tables + indexes)
        assert len(statements) >= 3, "Schema should have at least 3 statements"

        for stmt in statements:
            # Each statement should start with valid SQL or be a comment
            first_word = stmt.split()[0].upper() if stmt.split() else ""
            assert first_word in ("CREATE", "--", "INSERT"), (
                f"Unexpected statement start: {stmt[:50]}"
            )
            # No embedded semicolons that would break splitting
            assert ";" not in stmt, f"Statement contains embedded semicolon: {stmt[:50]}"


class TestSqlFeedbackStoreLifecycle:
    """Tests for SqlFeedbackStore lifecycle management."""

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, store: SqlFeedbackStore) -> None:
        """Calling close multiple times is safe."""
        await store.close()
        await store.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_operations_after_close_raise(self, store: SqlFeedbackStore) -> None:
        """Operations after close raise RuntimeError."""
        await store.close()

        with pytest.raises(RuntimeError, match="not initialized"):
            await store.record(make_interaction())

    @pytest.mark.asyncio
    async def test_reinitialize_after_close(self, db_env: str) -> None:
        """Store can be reinitialized after close."""
        store = SqlFeedbackStore()
        await store.initialize()
        await store.record(make_interaction(id="before-close"))
        await store.close()

        # Reinitialize
        await store.initialize()
        stats = await store.get_user_stats("123456789")
        assert stats[Outcome.ACCEPTED] == 1
        await store.close()
