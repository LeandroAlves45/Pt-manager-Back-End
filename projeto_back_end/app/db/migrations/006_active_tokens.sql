-- =============================================================================
-- Migration 006: Active Tokens
-- =============================================================================
--
-- Idempotent — safe to run multiple times (all statements use IF NOT EXISTS).
-- Runs automatically on container startup via migrate.py.
--
-- Purpose:
--   Persists JWT tokens in the database so that:
--     1. Logout invalidates the token immediately (stateless JWTs can't be revoked)
--     2. Developers can copy the active token from the DB into Swagger without re-logging in
--     3. A scheduled cleanup job removes expired tokens periodically
--
-- Behaviour:
--     Login  → INSERT or REPLACE into active_tokens (one row per user at most)
--     Request → get_current_user verifies token exists in this table
--     Logout  → DELETE the row (token is immediately invalid)
--     Scheduler → DELETE WHERE expires_at < NOW() every 60 minutes
-- =============================================================================
 
CREATE TABLE IF NOT EXISTS active_tokens (
    id          VARCHAR         PRIMARY KEY,
    user_id     VARCHAR         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- The full JWT string — stored so get_current_user can verify it exists
    token       TEXT            NOT NULL,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    -- Mirrors the JWT exp claim — used by the scheduler cleanup job
    expires_at  TIMESTAMPTZ     NOT NULL
);
 
-- Fast lookup by user_id (used on login to replace an existing token)
CREATE INDEX IF NOT EXISTS idx_active_tokens_user_id
    ON active_tokens (user_id);
 
-- Fast lookup by token string (used on every authenticated request)
CREATE INDEX IF NOT EXISTS idx_active_tokens_token
    ON active_tokens (token);
 
-- Fast cleanup by expiry (used by the scheduler job)
CREATE INDEX IF NOT EXISTS idx_active_tokens_expires_at
    ON active_tokens (expires_at);