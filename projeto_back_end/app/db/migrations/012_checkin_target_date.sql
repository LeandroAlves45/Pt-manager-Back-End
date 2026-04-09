-- Migration 013: add target_date to checkins table (AS-01)
--
-- Business reason:
--   The trainer needs to request a check-in for a specific future date
--   (e.g., "I want you to respond by April 20th").
--   The client sees this date on their dashboard and knows when to respond.
--
-- Design decisions:
--   - DATE type (no time) — the target date is a day, not an exact moment.
--   - Nullable — check-ins without a target date continue to work (backward compatibility).
--   - IF NOT EXISTS — idempotent; safe to re-run without errors.
--   - ADD COLUMN IF NOT EXISTS is supported from PostgreSQL 9.6 onwards (Neon uses PG 16).
 
ALTER TABLE checkins
  ADD COLUMN IF NOT EXISTS target_date DATE NULL;
 
-- Descriptive comment on the column for DB documentation
COMMENT ON COLUMN checkins.target_date IS
  'Target date requested by the trainer for the client to respond to the check-in. NULL = no specific date.';