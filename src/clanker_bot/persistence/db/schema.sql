-- Feedback persistence schema
-- Supports both SQLite (dev) and PostgreSQL (prod)
-- All tables keyed by guild_id for multi-server support

-- Interactions table: stores all user interaction outcomes
CREATE TABLE IF NOT EXISTS interactions (
    id TEXT PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    command TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (
        outcome IN ('accepted', 'rejected', 'regenerated', 'timeout')
    ),
    metadata TEXT,  -- JSON blob
    created_at TEXT NOT NULL
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
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    preferences TEXT NOT NULL DEFAULT '{}',  -- JSON blob
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, guild_id)
);

-- Guild configuration (future: prefix, enabled features, etc.)
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    config TEXT NOT NULL DEFAULT '{}',  -- JSON blob
    updated_at TEXT NOT NULL
);
