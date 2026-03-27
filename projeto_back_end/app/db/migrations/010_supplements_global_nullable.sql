-- =============================================================================
-- Migration 010: Allow NULL in supplements.created_by_user_id
-- =============================================================================
--
-- Idempotent — ALTER COLUMN ... DROP NOT NULL is safe to run multiple times
-- if already nullable (Postgres ignores it silently).
--
-- Problem being solved:
--   The supplements table was created with created_by_user_id NOT NULL,
--   but the catalogue seed inserts global supplements with NULL to mark them
--   as platform-wide (not owned by any trainer). This caused a NOT NULL
--   violation on startup.
--
-- Solution:
--   Drop the NOT NULL constraint so that:
--     NULL  → global supplement (visible to all trainers, managed by superuser)
--     value → trainer-owned supplement (private to that trainer)
-- =============================================================================

ALTER TABLE supplements
    ALTER COLUMN created_by_user_id DROP NOT NULL;
