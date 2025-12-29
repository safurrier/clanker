-- Interaction queries for sqlc
-- These define the SQL patterns used by SqlFeedbackStore

-- name: RecordInteraction :exec
INSERT INTO interactions (id, guild_id, user_id, command, outcome, metadata, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?);

-- name: GetUserStats :many
-- Returns outcome counts for a user, optionally filtered by guild/command
SELECT outcome, COUNT(*) as count
FROM interactions
WHERE user_id = ?
  AND (? IS NULL OR guild_id = ?)
  AND (? IS NULL OR command = ?)
GROUP BY outcome;

-- name: GetRecentInteractions :many
-- Returns recent interactions in reverse chronological order
SELECT id, guild_id, user_id, command, outcome, metadata, created_at
FROM interactions
WHERE user_id = ?
  AND (? IS NULL OR guild_id = ?)
  AND (? IS NULL OR command = ?)
ORDER BY created_at DESC
LIMIT ?;

-- name: GetAcceptanceRate :one
-- Calculate acceptance rate (accepted / total non-timeout)
SELECT
    CASE
        WHEN COUNT(*) = 0 THEN 0.5
        ELSE CAST(SUM(CASE WHEN outcome = 'accepted' THEN 1 ELSE 0 END) AS REAL) / COUNT(*)
    END as rate
FROM interactions
WHERE user_id = ?
  AND command = ?
  AND (? IS NULL OR guild_id = ?)
  AND outcome != 'timeout';

-- name: GetInteractionById :one
SELECT id, guild_id, user_id, command, outcome, metadata, created_at
FROM interactions
WHERE id = ?;
