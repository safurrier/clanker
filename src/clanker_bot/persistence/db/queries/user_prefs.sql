-- User preferences queries for sqlc

-- name: GetUserPreferences :one
SELECT user_id, guild_id, preferences, updated_at
FROM user_preferences
WHERE user_id = ? AND guild_id = ?;

-- name: UpsertUserPreferences :exec
INSERT INTO user_preferences (user_id, guild_id, preferences, updated_at)
VALUES (?, ?, ?, ?)
ON CONFLICT (user_id, guild_id)
DO UPDATE SET
    preferences = excluded.preferences,
    updated_at = excluded.updated_at;

-- name: GetGuildConfig :one
SELECT guild_id, config, updated_at
FROM guild_config
WHERE guild_id = ?;

-- name: UpsertGuildConfig :exec
INSERT INTO guild_config (guild_id, config, updated_at)
VALUES (?, ?, ?)
ON CONFLICT (guild_id)
DO UPDATE SET
    config = excluded.config,
    updated_at = excluded.updated_at;
