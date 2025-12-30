"""Database connection management with SQLite/Postgres switching.

Uses SQLAlchemy async engine for compatibility with sqlc-gen-python.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncConnection


def get_database_url() -> str:
    """Get DATABASE_URL from environment.

    Returns:
        Database URL string. Defaults to SQLite for local dev.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        # Default to SQLite for local dev
        return "sqlite+aiosqlite:///data/clanker.db"
    # Convert URL to SQLAlchemy format if needed
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///")
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://")
    return url


def is_sqlite() -> bool:
    """Check if using SQLite backend."""
    return "sqlite" in get_database_url()


# SQLAlchemy async engine (lazy initialized)
_engine: AsyncEngine | None = None


async def init_pool() -> None:
    """Initialize the SQLAlchemy async engine."""
    global _engine
    if _engine is not None:
        return

    url = get_database_url()

    if is_sqlite():
        # Ensure the data directory exists for SQLite
        db_path = url.replace("sqlite+aiosqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _engine = create_async_engine(url, echo=False)


async def close_pool() -> None:
    """Close the SQLAlchemy engine."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


def get_engine() -> AsyncEngine:
    """Get the SQLAlchemy async engine.

    Returns:
        The initialized async engine.

    Raises:
        RuntimeError: If the engine hasn't been initialized.
    """
    if _engine is None:
        raise RuntimeError("Engine not initialized. Call init_pool() first.")
    return _engine


@asynccontextmanager
async def get_connection() -> AsyncIterator[AsyncConnection]:
    """Get a database connection from the engine.

    Yields:
        SQLAlchemy AsyncConnection for executing queries.
    """
    global _engine
    if _engine is None:
        await init_pool()

    assert _engine is not None  # For type checker
    async with _engine.begin() as conn:
        yield conn


# Legacy compatibility: also expose raw aiosqlite connection for tests
@asynccontextmanager
async def get_raw_connection() -> AsyncIterator[Any]:
    """Get a raw aiosqlite connection for direct SQL execution.

    This is primarily for tests that need direct database access.
    For normal operations, use get_connection() with SQLAlchemy.

    Yields:
        aiosqlite.Connection for direct SQL execution.
    """
    if not is_sqlite():
        raise RuntimeError("get_raw_connection() only works with SQLite")

    url = get_database_url().replace("sqlite+aiosqlite:///", "")
    Path(url).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(url) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn
