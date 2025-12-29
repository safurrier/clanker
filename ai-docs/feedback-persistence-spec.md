# Feedback Persistence Layer - Spec & TDD Plan

## Overview

Add a persistence layer to track user interaction outcomes (post/dismiss/regenerate) across commands. This enables:
1. **Feedback loop** - Learn which content users accept vs reject
2. **User preferences** - Track per-user style preferences over time
3. **Rate limiting** - Prevent abuse based on usage patterns
4. **Analytics** - Understand what works across guilds/users

## Architecture Decision: SDK Protocol (Approach B)

The feedback system uses the SDK Protocol pattern, consistent with existing providers (LLM, TTS, STT):

```
┌─────────────────────────────────────────────────────────────────┐
│ SDK Layer (src/clanker/)                                        │
│  ├── models.py          → Interaction, Outcome, UserPrefs       │
│  └── providers/         → FeedbackStore protocol                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Bot Layer (src/clanker_bot/)                                    │
│  ├── persistence/                                               │
│  │    ├── db/                                                   │
│  │    │    ├── schema.sql        → Table definitions            │
│  │    │    └── queries/                                         │
│  │    │         ├── interactions.sql  → sqlc query definitions  │
│  │    │         └── user_prefs.sql                              │
│  │    ├── generated/             → sqlc-gen-python output       │
│  │    │    ├── models.py         → Pydantic row models          │
│  │    │    └── queries.py        → Typed async query methods    │
│  │    ├── sqlc.yaml              → sqlc configuration           │
│  │    ├── connection.py          → DATABASE_URL switching       │
│  │    └── sql_feedback.py        → FeedbackStore implementation │
│  ├── command_handlers/  → Records interactions via protocol     │
│  └── views/             → Button callbacks trigger recording    │
└─────────────────────────────────────────────────────────────────┘
```

## Database Strategy

**SQL-first approach with sqlc-gen-python:**
- SQLite for local development (zero config)
- Neon Postgres for production (hosted, serverless)
- `DATABASE_URL` env var switches between them
- sqlc generates typed Python query wrappers from SQL files
- No ORM - explicit, reviewable SQL

**Key principles:**
- All data keyed by `guild_id` (Discord's multi-server model)
- Single bot instance across many guilds
- UPSERT patterns for config/preferences
- psycopg3 (sync) or asyncpg (async) drivers

## SDK Components

### 1. Models (`src/clanker/models.py`)

```python
from enum import Enum

class Outcome(str, Enum):
    """Outcome of a user interaction."""
    ACCEPTED = "accepted"      # User posted/confirmed content
    REJECTED = "rejected"      # User dismissed/cancelled
    REGENERATED = "regenerated"  # User requested new generation
    TIMEOUT = "timeout"        # View timed out without action


@dataclass(frozen=True)
class Interaction:
    """A recorded user interaction with generated content.

    Uses string IDs for platform-agnosticism (Discord uses int,
    but web/CLI could use UUIDs).
    """
    id: str                           # Unique interaction ID
    user_id: str                      # Platform user identifier
    context_id: str                   # Guild/server/app context
    command: str                      # Command name (shitpost, chat, etc)
    outcome: Outcome                  # What the user did
    metadata: Mapping[str, Any]       # Command-specific data
    created_at: datetime              # When interaction occurred


@dataclass(frozen=True)
class UserPreferences:
    """Aggregated user preferences derived from interactions."""
    user_id: str
    context_id: str
    preferences: Mapping[str, Any]    # Flexible schema for prefs
    updated_at: datetime
```

### 2. Protocol (`src/clanker/providers/feedback.py`)

```python
from typing import Protocol
from collections.abc import Sequence


class FeedbackStore(Protocol):
    """Protocol for storing and retrieving interaction feedback."""

    async def record(self, interaction: Interaction) -> None:
        """Record a user interaction outcome.

        Args:
            interaction: The interaction to store

        Raises:
            TransientProviderError: Temporary storage failure (retry)
            PermanentProviderError: Unrecoverable failure
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

        Returns:
            Float 0.0-1.0, or 0.5 if no data
        """
        ...
```

## Bot Components

### 3. sqlc Configuration (`src/clanker_bot/persistence/sqlc.yaml`)

```yaml
version: "2"
plugins:
  - name: py
    wasm:
      url: https://downloads.sqlc.dev/plugin/sqlc-gen-python_1.0.0.wasm
      sha256: <sha256>
sql:
  - schema: "db/schema.sql"
    queries: "db/queries"
    engine: "postgresql"  # sqlc uses postgres syntax, works with both
    codegen:
      - plugin: py
        out: "generated"
        options:
          package: "generated"
          emit_pydantic_models: true
          emit_async: true
```

### 4. Schema (`src/clanker_bot/persistence/db/schema.sql`)

```sql
-- Interactions table: stores all user interaction outcomes
-- All tables keyed by guild_id for multi-server support
CREATE TABLE IF NOT EXISTS interactions (
    id TEXT PRIMARY KEY,
    guild_id BIGINT NOT NULL,         -- Discord guild (context_id)
    user_id BIGINT NOT NULL,          -- Discord user
    command TEXT NOT NULL,
    outcome TEXT NOT NULL,
    metadata JSONB,                   -- Flexible per-command data
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_outcome CHECK (
        outcome IN ('accepted', 'rejected', 'regenerated', 'timeout')
    )
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_interactions_user
    ON interactions(user_id, command, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_interactions_guild
    ON interactions(guild_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_interactions_user_guild
    ON interactions(user_id, guild_id, command);

-- User preferences: aggregated/computed preferences per guild
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id BIGINT NOT NULL,
    guild_id BIGINT NOT NULL,
    preferences JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (user_id, guild_id)
);

-- Guild configuration (future: prefix, enabled features, etc.)
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id BIGINT PRIMARY KEY,
    config JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 5. sqlc Queries (`src/clanker_bot/persistence/db/queries/interactions.sql`)

```sql
-- name: RecordInteraction :exec
INSERT INTO interactions (id, guild_id, user_id, command, outcome, metadata, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7);

-- name: GetUserStats :many
-- Returns outcome counts for a user, optionally filtered by guild/command
SELECT outcome, COUNT(*)::int as count
FROM interactions
WHERE user_id = $1
  AND ($2::bigint IS NULL OR guild_id = $2)
  AND ($3::text IS NULL OR command = $3)
GROUP BY outcome;

-- name: GetRecentInteractions :many
-- Returns recent interactions in reverse chronological order
SELECT id, guild_id, user_id, command, outcome, metadata, created_at
FROM interactions
WHERE user_id = $1
  AND ($2::bigint IS NULL OR guild_id = $2)
  AND ($3::text IS NULL OR command = $3)
ORDER BY created_at DESC
LIMIT $4;

-- name: GetAcceptanceRate :one
-- Calculate acceptance rate (accepted / total non-timeout)
SELECT
    CASE
        WHEN COUNT(*) = 0 THEN 0.5
        ELSE COUNT(*) FILTER (WHERE outcome = 'accepted')::float / COUNT(*)::float
    END as rate
FROM interactions
WHERE user_id = $1
  AND command = $2
  AND ($3::bigint IS NULL OR guild_id = $3)
  AND outcome != 'timeout';

-- name: GetInteractionById :one
SELECT id, guild_id, user_id, command, outcome, metadata, created_at
FROM interactions
WHERE id = $1;
```

### 6. sqlc Queries (`src/clanker_bot/persistence/db/queries/user_prefs.sql`)

```sql
-- name: GetUserPreferences :one
SELECT user_id, guild_id, preferences, updated_at
FROM user_preferences
WHERE user_id = $1 AND guild_id = $2;

-- name: UpsertUserPreferences :one
INSERT INTO user_preferences (user_id, guild_id, preferences, updated_at)
VALUES ($1, $2, $3, now())
ON CONFLICT (user_id, guild_id)
DO UPDATE SET
    preferences = EXCLUDED.preferences,
    updated_at = now()
RETURNING user_id, guild_id, preferences, updated_at;

-- name: GetGuildConfig :one
SELECT guild_id, config, updated_at
FROM guild_config
WHERE guild_id = $1;

-- name: UpsertGuildConfig :one
INSERT INTO guild_config (guild_id, config, updated_at)
VALUES ($1, $2, now())
ON CONFLICT (guild_id)
DO UPDATE SET
    config = EXCLUDED.config,
    updated_at = now()
RETURNING guild_id, config, updated_at;
```

### 7. Connection Management (`src/clanker_bot/persistence/connection.py`)

```python
"""Database connection management with SQLite/Postgres switching."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from asyncpg import Connection

# Connection pool (lazy initialized)
_pool: asyncpg.Pool | None = None


def get_database_url() -> str:
    """Get DATABASE_URL from environment.

    Returns:
        Database URL string

    Raises:
        RuntimeError: If DATABASE_URL not set
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        # Default to SQLite for local dev
        return "sqlite:///data/clanker.db"
    return url


def is_sqlite() -> bool:
    """Check if using SQLite backend."""
    return get_database_url().startswith("sqlite")


async def init_pool() -> None:
    """Initialize the connection pool."""
    global _pool
    if _pool is not None:
        return

    url = get_database_url()
    if is_sqlite():
        # aiosqlite for async SQLite
        import aiosqlite
        # SQLite doesn't use pools, handled per-connection
        return

    import asyncpg
    _pool = await asyncpg.create_pool(url, min_size=1, max_size=10)


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection() -> AsyncIterator[Connection]:
    """Get a database connection from the pool.

    Yields:
        Database connection (asyncpg.Connection or aiosqlite.Connection)
    """
    if is_sqlite():
        import aiosqlite
        url = get_database_url().replace("sqlite:///", "")
        async with aiosqlite.connect(url) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn
    else:
        if _pool is None:
            await init_pool()
        async with _pool.acquire() as conn:
            yield conn
```

### 8. Implementation (`src/clanker_bot/persistence/sql_feedback.py`)

```python
"""FeedbackStore implementation using sqlc-generated queries."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from clanker.models import Interaction, Outcome, UserPreferences
from clanker.providers.feedback import FeedbackStore
from clanker.providers.errors import PermanentProviderError, TransientProviderError

from .connection import get_connection, init_pool, close_pool
from .generated.queries import Queries  # sqlc-generated


@dataclass
class SqlFeedbackStore:
    """SQLite/Postgres implementation of FeedbackStore.

    Uses sqlc-generated query methods for type-safe database access.
    """

    _initialized: bool = False

    async def initialize(self) -> None:
        """Initialize connection pool and run schema migrations."""
        if self._initialized:
            return
        await init_pool()
        # Run schema migrations
        async with get_connection() as conn:
            schema_path = Path(__file__).parent / "db" / "schema.sql"
            schema = schema_path.read_text()
            await conn.execute(schema)
        self._initialized = True

    async def close(self) -> None:
        """Close connection pool."""
        await close_pool()
        self._initialized = False

    async def record(self, interaction: Interaction) -> None:
        """Record a user interaction outcome."""
        if not self._initialized:
            raise RuntimeError("Store not initialized")

        async with get_connection() as conn:
            queries = Queries(conn)
            try:
                await queries.record_interaction(
                    id=interaction.id,
                    guild_id=int(interaction.context_id),
                    user_id=int(interaction.user_id),
                    command=interaction.command,
                    outcome=interaction.outcome.value,
                    metadata=json.dumps(interaction.metadata),
                    created_at=interaction.created_at,
                )
            except Exception as e:
                if "UNIQUE constraint" in str(e) or "duplicate key" in str(e):
                    raise PermanentProviderError(f"Duplicate interaction ID: {interaction.id}") from e
                raise TransientProviderError(f"Failed to record interaction: {e}") from e

    async def get_user_stats(
        self,
        user_id: str,
        context_id: str | None = None,
        command: str | None = None,
    ) -> Mapping[Outcome, int]:
        """Get outcome counts for a user."""
        if not self._initialized:
            raise RuntimeError("Store not initialized")

        async with get_connection() as conn:
            queries = Queries(conn)
            rows = await queries.get_user_stats(
                user_id=int(user_id),
                guild_id=int(context_id) if context_id else None,
                command=command,
            )
            return {Outcome(row.outcome): row.count for row in rows}

    async def get_recent_interactions(
        self,
        user_id: str,
        context_id: str | None = None,
        command: str | None = None,
        limit: int = 100,
    ) -> Sequence[Interaction]:
        """Get recent interactions in reverse chronological order."""
        if not self._initialized:
            raise RuntimeError("Store not initialized")

        async with get_connection() as conn:
            queries = Queries(conn)
            rows = await queries.get_recent_interactions(
                user_id=int(user_id),
                guild_id=int(context_id) if context_id else None,
                command=command,
                limit=limit,
            )
            return [
                Interaction(
                    id=row.id,
                    user_id=str(row.user_id),
                    context_id=str(row.guild_id),
                    command=row.command,
                    outcome=Outcome(row.outcome),
                    metadata=json.loads(row.metadata) if row.metadata else {},
                    created_at=row.created_at,
                )
                for row in rows
            ]

    async def get_acceptance_rate(
        self,
        user_id: str,
        command: str,
        context_id: str | None = None,
    ) -> float:
        """Calculate acceptance rate for a user/command."""
        if not self._initialized:
            raise RuntimeError("Store not initialized")

        async with get_connection() as conn:
            queries = Queries(conn)
            result = await queries.get_acceptance_rate(
                user_id=int(user_id),
                command=command,
                guild_id=int(context_id) if context_id else None,
            )
            return result.rate if result else 0.5
```

### 5. Integration Points

**BotDependencies** (`src/clanker_bot/command_handlers/types.py`):
```python
@dataclass(frozen=True)
class BotDependencies:
    # ... existing fields
    feedback_store: FeedbackStore | None = None
```

**ShitpostPreviewView** (`src/clanker_bot/views/shitpost_preview.py`):
```python
class ShitpostPreviewView(discord.ui.View):
    def __init__(
        self,
        *,
        # ... existing params
        feedback_store: FeedbackStore | None = None,
    ):
        self.feedback_store = feedback_store

    async def _record_outcome(self, outcome: Outcome) -> None:
        """Fire-and-forget interaction recording."""
        if self.feedback_store is None:
            return
        interaction = Interaction(
            id=self.preview_id,
            user_id=str(self.invoker_id),
            context_id=str(self.guild_id),
            command="shitpost",
            outcome=outcome,
            metadata={"template_id": self.payload.template_id},
            created_at=datetime.now(timezone.utc),
        )
        # Fire and forget with error logging
        asyncio.create_task(self._safe_record(interaction))
```

---

## TDD Implementation Plan

### Phase 1: SDK Models & Protocol

#### Test File: `tests/test_feedback_models.py`

```python
# Test 1.1: Outcome enum values
def test_outcome_enum_values():
    """Outcome enum has expected string values."""
    assert Outcome.ACCEPTED.value == "accepted"
    assert Outcome.REJECTED.value == "rejected"
    assert Outcome.REGENERATED.value == "regenerated"
    assert Outcome.TIMEOUT.value == "timeout"

# Test 1.2: Interaction is frozen/immutable
def test_interaction_frozen():
    """Interaction dataclass is immutable."""
    interaction = Interaction(
        id="test-123",
        user_id="user-456",
        context_id="guild-789",
        command="shitpost",
        outcome=Outcome.ACCEPTED,
        metadata={"template": "drake"},
        created_at=datetime.now(timezone.utc),
    )
    with pytest.raises(FrozenInstanceError):
        interaction.outcome = Outcome.REJECTED

# Test 1.3: Interaction with minimal metadata
def test_interaction_empty_metadata():
    """Interaction works with empty metadata."""
    interaction = Interaction(
        id="test-123",
        user_id="user-456",
        context_id="guild-789",
        command="chat",
        outcome=Outcome.ACCEPTED,
        metadata={},
        created_at=datetime.now(timezone.utc),
    )
    assert interaction.metadata == {}

# Test 1.4: UserPreferences is frozen
def test_user_preferences_frozen():
    """UserPreferences dataclass is immutable."""
    prefs = UserPreferences(
        user_id="user-123",
        context_id="guild-456",
        preferences={"preferred_style": "edgy"},
        updated_at=datetime.now(timezone.utc),
    )
    with pytest.raises(FrozenInstanceError):
        prefs.preferences = {}
```

**Implementation**: Add `Outcome`, `Interaction`, `UserPreferences` to `src/clanker/models.py`

---

#### Test File: `tests/test_feedback_protocol.py`

```python
# Test 1.5: FakeFeedbackStore implements protocol
def test_fake_feedback_store_implements_protocol():
    """FakeFeedbackStore satisfies FeedbackStore protocol."""
    fake = FakeFeedbackStore()
    assert isinstance(fake, FeedbackStore)

# Test 1.6: FakeFeedbackStore records interactions
@pytest.mark.asyncio
async def test_fake_feedback_store_records():
    """FakeFeedbackStore stores and retrieves interactions."""
    fake = FakeFeedbackStore()
    interaction = make_interaction(outcome=Outcome.ACCEPTED)

    await fake.record(interaction)

    assert len(fake.interactions) == 1
    assert fake.interactions[0] == interaction

# Test 1.7: FakeFeedbackStore get_user_stats
@pytest.mark.asyncio
async def test_fake_feedback_store_user_stats():
    """FakeFeedbackStore computes user stats correctly."""
    fake = FakeFeedbackStore()
    await fake.record(make_interaction(outcome=Outcome.ACCEPTED))
    await fake.record(make_interaction(outcome=Outcome.ACCEPTED))
    await fake.record(make_interaction(outcome=Outcome.REJECTED))

    stats = await fake.get_user_stats("user-123")

    assert stats[Outcome.ACCEPTED] == 2
    assert stats[Outcome.REJECTED] == 1

# Test 1.8: FakeFeedbackStore acceptance rate calculation
@pytest.mark.asyncio
async def test_fake_feedback_store_acceptance_rate():
    """Acceptance rate calculated correctly."""
    fake = FakeFeedbackStore()
    # 3 accepted, 1 rejected = 75% acceptance
    for _ in range(3):
        await fake.record(make_interaction(outcome=Outcome.ACCEPTED))
    await fake.record(make_interaction(outcome=Outcome.REJECTED))

    rate = await fake.get_acceptance_rate("user-123", "shitpost")

    assert rate == 0.75

# Test 1.9: Acceptance rate with no data returns 0.5
@pytest.mark.asyncio
async def test_acceptance_rate_no_data():
    """Acceptance rate returns 0.5 when no data exists."""
    fake = FakeFeedbackStore()
    rate = await fake.get_acceptance_rate("unknown-user", "shitpost")
    assert rate == 0.5
```

**Implementation**:
1. Add `FeedbackStore` protocol to `src/clanker/providers/feedback.py`
2. Add `FakeFeedbackStore` to `tests/fakes.py`
3. Export from `src/clanker/providers/__init__.py`

---

### Phase 2: SQL Implementation

#### Test File: `tests/test_sql_feedback.py`

```python
# Test 2.1: Schema creates tables
@pytest.mark.asyncio
async def test_schema_creates_tables(tmp_path):
    """Schema SQL creates expected tables."""
    db_path = tmp_path / "test.db"
    store = SqlFeedbackStore(f"sqlite:///{db_path}")
    await store.initialize()

    # Verify tables exist
    async with store._get_conn() as conn:
        result = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in await result.fetchall()}

    assert "interactions" in tables
    assert "user_preferences" in tables
    await store.close()

# Test 2.2: Record interaction inserts row
@pytest.mark.asyncio
async def test_record_interaction(tmp_path):
    """Recording an interaction inserts a database row."""
    store = await create_test_store(tmp_path)
    interaction = make_interaction()

    await store.record(interaction)

    async with store._get_conn() as conn:
        result = await conn.execute(
            "SELECT * FROM interactions WHERE id = ?",
            (interaction.id,)
        )
        row = await result.fetchone()

    assert row is not None
    assert row["user_id"] == interaction.user_id
    assert row["outcome"] == interaction.outcome.value
    await store.close()

# Test 2.3: Record interaction with metadata
@pytest.mark.asyncio
async def test_record_interaction_with_metadata(tmp_path):
    """Metadata is JSON-serialized correctly."""
    store = await create_test_store(tmp_path)
    interaction = make_interaction(
        metadata={"template": "drake", "length": 42}
    )

    await store.record(interaction)

    async with store._get_conn() as conn:
        result = await conn.execute(
            "SELECT metadata FROM interactions WHERE id = ?",
            (interaction.id,)
        )
        row = await result.fetchone()

    metadata = json.loads(row["metadata"])
    assert metadata["template"] == "drake"
    assert metadata["length"] == 42
    await store.close()

# Test 2.4: Get user stats aggregates correctly
@pytest.mark.asyncio
async def test_get_user_stats(tmp_path):
    """User stats aggregated by outcome."""
    store = await create_test_store(tmp_path)

    # Record mixed outcomes
    for outcome, count in [
        (Outcome.ACCEPTED, 5),
        (Outcome.REJECTED, 2),
        (Outcome.REGENERATED, 3),
    ]:
        for _ in range(count):
            await store.record(make_interaction(outcome=outcome))

    stats = await store.get_user_stats("user-123")

    assert stats[Outcome.ACCEPTED] == 5
    assert stats[Outcome.REJECTED] == 2
    assert stats[Outcome.REGENERATED] == 3
    await store.close()

# Test 2.5: Get user stats with context filter
@pytest.mark.asyncio
async def test_get_user_stats_context_filter(tmp_path):
    """User stats filtered by context_id."""
    store = await create_test_store(tmp_path)

    # Guild A: 3 accepted
    for _ in range(3):
        await store.record(make_interaction(
            context_id="guild-A",
            outcome=Outcome.ACCEPTED
        ))
    # Guild B: 2 accepted
    for _ in range(2):
        await store.record(make_interaction(
            context_id="guild-B",
            outcome=Outcome.ACCEPTED
        ))

    stats_a = await store.get_user_stats("user-123", context_id="guild-A")
    stats_b = await store.get_user_stats("user-123", context_id="guild-B")

    assert stats_a[Outcome.ACCEPTED] == 3
    assert stats_b[Outcome.ACCEPTED] == 2
    await store.close()

# Test 2.6: Get recent interactions
@pytest.mark.asyncio
async def test_get_recent_interactions(tmp_path):
    """Recent interactions returned in reverse chronological order."""
    store = await create_test_store(tmp_path)

    # Record interactions with different timestamps
    now = datetime.now(timezone.utc)
    for i in range(5):
        await store.record(make_interaction(
            id=f"interaction-{i}",
            created_at=now - timedelta(minutes=i),
        ))

    recent = await store.get_recent_interactions("user-123", limit=3)

    assert len(recent) == 3
    assert recent[0].id == "interaction-0"  # Most recent first
    assert recent[2].id == "interaction-2"
    await store.close()

# Test 2.7: Acceptance rate calculation
@pytest.mark.asyncio
async def test_acceptance_rate(tmp_path):
    """Acceptance rate calculated from outcomes."""
    store = await create_test_store(tmp_path)

    # 4 accepted, 1 rejected, 1 regenerated = 4/6 = 66.7%
    for _ in range(4):
        await store.record(make_interaction(outcome=Outcome.ACCEPTED))
    await store.record(make_interaction(outcome=Outcome.REJECTED))
    await store.record(make_interaction(outcome=Outcome.REGENERATED))

    rate = await store.get_acceptance_rate("user-123", "shitpost")

    assert abs(rate - 0.667) < 0.01
    await store.close()

# Test 2.8: Duplicate interaction ID raises error
@pytest.mark.asyncio
async def test_duplicate_interaction_raises(tmp_path):
    """Recording duplicate interaction ID raises error."""
    store = await create_test_store(tmp_path)
    interaction = make_interaction(id="duplicate-123")

    await store.record(interaction)

    with pytest.raises(PermanentProviderError):
        await store.record(interaction)
    await store.close()

# Test 2.9: Invalid outcome rejected by constraint
@pytest.mark.asyncio
async def test_invalid_outcome_rejected(tmp_path):
    """Database constraint rejects invalid outcome values."""
    store = await create_test_store(tmp_path)

    # Bypass model validation to test DB constraint
    async with store._get_conn() as conn:
        with pytest.raises(Exception):  # IntegrityError
            await conn.execute(
                "INSERT INTO interactions VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("test", "user", "ctx", "cmd", "invalid_outcome", "{}", "2024-01-01")
            )
    await store.close()
```

**Implementation**: `src/clanker_bot/persistence/sql_feedback.py`

---

### Phase 3: Bot Integration

#### Test File: `tests/test_feedback_integration.py`

```python
# Test 3.1: ShitpostPreviewView records accepted outcome
@pytest.mark.asyncio
async def test_shitpost_post_records_accepted():
    """Posting shitpost records ACCEPTED outcome."""
    fake_store = FakeFeedbackStore()
    view = ShitpostPreviewView(
        invoker_id=123,
        payload=MemePayload(text="test"),
        embed=discord.Embed(),
        feedback_store=fake_store,
        guild_id=456,
    )

    # Simulate post button click
    await view._record_outcome(Outcome.ACCEPTED)

    assert len(fake_store.interactions) == 1
    assert fake_store.interactions[0].outcome == Outcome.ACCEPTED
    assert fake_store.interactions[0].command == "shitpost"

# Test 3.2: ShitpostPreviewView records rejected outcome
@pytest.mark.asyncio
async def test_shitpost_dismiss_records_rejected():
    """Dismissing shitpost records REJECTED outcome."""
    fake_store = FakeFeedbackStore()
    view = ShitpostPreviewView(
        invoker_id=123,
        payload=MemePayload(text="test"),
        embed=discord.Embed(),
        feedback_store=fake_store,
        guild_id=456,
    )

    await view._record_outcome(Outcome.REJECTED)

    assert fake_store.interactions[0].outcome == Outcome.REJECTED

# Test 3.3: ShitpostPreviewView records regenerated outcome
@pytest.mark.asyncio
async def test_shitpost_regenerate_records_regenerated():
    """Regenerating shitpost records REGENERATED outcome."""
    fake_store = FakeFeedbackStore()
    view = ShitpostPreviewView(
        invoker_id=123,
        payload=MemePayload(text="test"),
        embed=discord.Embed(),
        feedback_store=fake_store,
        guild_id=456,
    )

    await view._record_outcome(Outcome.REGENERATED)

    assert fake_store.interactions[0].outcome == Outcome.REGENERATED

# Test 3.4: Recording failure doesn't break UI flow
@pytest.mark.asyncio
async def test_recording_failure_graceful():
    """Recording failure doesn't prevent UI action."""
    failing_store = FailingFeedbackStore()  # Always raises
    view = ShitpostPreviewView(
        invoker_id=123,
        payload=MemePayload(text="test"),
        embed=discord.Embed(),
        feedback_store=failing_store,
        guild_id=456,
    )

    # Should not raise - failure is logged but swallowed
    await view._record_outcome(Outcome.ACCEPTED)
    # Test passes if no exception

# Test 3.5: No feedback store is gracefully handled
@pytest.mark.asyncio
async def test_no_feedback_store():
    """View works correctly without feedback store."""
    view = ShitpostPreviewView(
        invoker_id=123,
        payload=MemePayload(text="test"),
        embed=discord.Embed(),
        feedback_store=None,  # Not configured
        guild_id=456,
    )

    # Should not raise
    await view._record_outcome(Outcome.ACCEPTED)

# Test 3.6: Metadata includes template info
@pytest.mark.asyncio
async def test_metadata_includes_template():
    """Recorded interaction includes template metadata."""
    fake_store = FakeFeedbackStore()
    view = ShitpostPreviewView(
        invoker_id=123,
        payload=MemePayload(text="test", template_id="drake"),
        embed=discord.Embed(),
        feedback_store=fake_store,
        guild_id=456,
    )

    await view._record_outcome(Outcome.ACCEPTED)

    assert fake_store.interactions[0].metadata["template_id"] == "drake"

# Test 3.7: BotDependencies includes feedback_store
def test_bot_dependencies_feedback_store():
    """BotDependencies has feedback_store field."""
    deps = BotDependencies(
        llm=FakeLLM(),
        stt=None,
        tts=None,
        persona=make_persona(),
        voice_manager=Mock(),
        feedback_store=FakeFeedbackStore(),
    )
    assert deps.feedback_store is not None
```

**Implementation**:
1. Update `ShitpostPreviewView` to accept and use `feedback_store`
2. Add `feedback_store` field to `BotDependencies`
3. Wire up in `main.py` startup

---

### Phase 4: Database Lifecycle

#### Test File: `tests/test_db_lifecycle.py`

```python
# Test 4.1: Database created on first run
@pytest.mark.asyncio
async def test_database_created(tmp_path):
    """Database file created on initialize."""
    db_path = tmp_path / "test.db"
    assert not db_path.exists()

    store = SqlFeedbackStore(f"sqlite:///{db_path}")
    await store.initialize()

    assert db_path.exists()
    await store.close()

# Test 4.2: Multiple initialize calls are idempotent
@pytest.mark.asyncio
async def test_initialize_idempotent(tmp_path):
    """Calling initialize multiple times is safe."""
    store = await create_test_store(tmp_path)

    # Record some data
    await store.record(make_interaction())

    # Re-initialize
    await store.initialize()

    # Data should still exist
    stats = await store.get_user_stats("user-123")
    assert stats[Outcome.ACCEPTED] == 1
    await store.close()

# Test 4.3: Close is idempotent
@pytest.mark.asyncio
async def test_close_idempotent(tmp_path):
    """Calling close multiple times is safe."""
    store = await create_test_store(tmp_path)

    await store.close()
    await store.close()  # Should not raise

# Test 4.4: Operations after close raise error
@pytest.mark.asyncio
async def test_operations_after_close_raise(tmp_path):
    """Operations after close raise appropriate error."""
    store = await create_test_store(tmp_path)
    await store.close()

    with pytest.raises(RuntimeError):
        await store.record(make_interaction())
```

---

## Implementation Order

### Phase 1: SDK Models & Protocol
**Tests 1.1-1.9**

1. **SDK Models** (Tests 1.1-1.4)
   - Add `Outcome` enum to `models.py`
   - Add `Interaction` frozen dataclass
   - Add `UserPreferences` frozen dataclass

2. **Protocol & Fake** (Tests 1.5-1.9)
   - Add `FeedbackStore` protocol to `providers/feedback.py`
   - Add `FakeFeedbackStore` to `tests/fakes.py`
   - Export from `providers/__init__.py`

### Phase 2: sqlc Setup & SQL Schema
**Tests 2.1-2.3**

3. **sqlc Configuration**
   - Create `persistence/sqlc.yaml`
   - Create `persistence/db/schema.sql`
   - Create `persistence/db/queries/interactions.sql`
   - Create `persistence/db/queries/user_prefs.sql`
   - Run `sqlc generate` to create `generated/` files
   - Add `asyncpg`, `aiosqlite` to dependencies

4. **Connection Management**
   - Create `persistence/connection.py`
   - Implement `DATABASE_URL` switching (SQLite vs Postgres)
   - Implement `init_pool()`, `close_pool()`, `get_connection()`

### Phase 3: SQL Implementation
**Tests 2.4-2.9**

5. **SqlFeedbackStore - Basic**
   - Create `persistence/sql_feedback.py`
   - Implement `initialize()` with schema migration
   - Implement `record()` using sqlc `RecordInteraction`

6. **SqlFeedbackStore - Queries**
   - Implement `get_user_stats()` using sqlc `GetUserStats`
   - Implement `get_recent_interactions()` using sqlc `GetRecentInteractions`
   - Implement `get_acceptance_rate()` using sqlc `GetAcceptanceRate`

### Phase 4: Bot Integration
**Tests 3.1-3.7**

7. **View Integration**
   - Update `ShitpostPreviewView` to accept `feedback_store`
   - Add `_record_outcome()` helper method
   - Wire into post/dismiss/regenerate button handlers

8. **Dependency Injection**
   - Add `feedback_store` field to `BotDependencies`
   - Initialize `SqlFeedbackStore` in `main.py`
   - Pass through to views/handlers

### Phase 5: Lifecycle & Polish
**Tests 4.1-4.4**

9. **Lifecycle Management**
   - Idempotent `initialize()` and `close()`
   - Graceful error handling (don't crash bot on DB issues)
   - Connection pool tuning

10. **CI Integration**
    - Add `sqlc generate` check to CI
    - Verify generated code is committed and up to date

---

## Files to Create/Modify

### New Files
```
src/clanker/providers/feedback.py          # FeedbackStore protocol
src/clanker_bot/persistence/
├── __init__.py                            # Package exports
├── sqlc.yaml                              # sqlc configuration
├── connection.py                          # DATABASE_URL switching
├── sql_feedback.py                        # FeedbackStore implementation
├── db/
│   ├── schema.sql                         # Table definitions
│   └── queries/
│       ├── interactions.sql               # Interaction queries
│       └── user_prefs.sql                 # Preferences queries
└── generated/                             # sqlc output (maybe gitignored)
    ├── models.py                          # Pydantic row models
    └── queries.py                         # Typed query methods

tests/
├── test_feedback_models.py                # SDK model tests
├── test_feedback_protocol.py              # Protocol/fake tests
├── test_sql_feedback.py                   # SQL implementation tests
├── test_feedback_integration.py           # Bot integration tests
└── test_db_lifecycle.py                   # Connection lifecycle tests
```

### Modified Files
- `src/clanker/models.py` - Add `Outcome`, `Interaction`, `UserPreferences`
- `src/clanker/providers/__init__.py` - Export `FeedbackStore`
- `src/clanker_bot/views/shitpost_preview.py` - Add feedback recording
- `src/clanker_bot/command_handlers/types.py` - Add `feedback_store` to deps
- `src/clanker_bot/main.py` - Initialize and inject feedback store
- `tests/fakes.py` - Add `FakeFeedbackStore`
- `pyproject.toml` - Add `asyncpg`, `aiosqlite` dependencies

### Dependencies to Add
```toml
# pyproject.toml
dependencies = [
    # ... existing
    "asyncpg>=0.29.0",      # Postgres async driver
    "aiosqlite>=0.19.0",    # SQLite async driver
]

[project.optional-dependencies]
dev = [
    # ... existing
    "sqlc>=...",            # SQL compiler (installed via brew/binary)
]
```

---

## sqlc Workflow

**Initial setup:**
```bash
# Install sqlc (macOS)
brew install sqlc

# Generate Python code from SQL
cd src/clanker_bot/persistence
sqlc generate
```

**After modifying queries:**
```bash
# Regenerate after changing .sql files
cd src/clanker_bot/persistence
sqlc generate

# Verify types
make ty
```

**CI integration:**
```yaml
# In CI, verify generated code is up to date
- run: |
    cd src/clanker_bot/persistence
    sqlc generate
    git diff --exit-code generated/
```

---

## Future Extensions (Not in Scope)

- User preference computation from interactions
- Rate limiting based on usage
- Analytics dashboard/export
- Pruning old interactions
- Transcript persistence (separate spec planned)
