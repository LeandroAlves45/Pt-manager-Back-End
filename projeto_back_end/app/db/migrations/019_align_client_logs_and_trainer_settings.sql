-- ============================================================================
-- Migration 019: align client exercise logs and trainer settings
-- ============================================================================
--
-- Aligns existing databases with the current application contract:
-- 1. client_exercise_set_logs now enforces the same required fields and value
--    ranges already expected by the ORM and API schemas.
-- 2. trainer_settings is kept on the date-only convention used across the
--    training domain, and logo_public_id is widened to match the model.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. CLIENT_EXERCISE_SET_LOGS
-- ---------------------------------------------------------------------------

-- Backfill missing dates before making the columns required.
UPDATE client_exercise_set_logs
SET logged_at = CURRENT_DATE
WHERE logged_at IS NULL;

UPDATE client_exercise_set_logs
SET updated_at = COALESCE(updated_at, logged_at, CURRENT_DATE)
WHERE updated_at IS NULL;

-- Keep the existing table contract aligned with the ORM model.
ALTER TABLE client_exercise_set_logs
    ALTER COLUMN logged_at SET NOT NULL;

ALTER TABLE client_exercise_set_logs
    ALTER COLUMN updated_at SET NOT NULL;

-- Normalize the unique constraint name across SQL and SQLModel.
ALTER TABLE client_exercise_set_logs
    DROP CONSTRAINT IF EXISTS uix_client_exercise_set;

ALTER TABLE client_exercise_set_logs
    DROP CONSTRAINT IF EXISTS uix_client_exercise_set_log;

ALTER TABLE client_exercise_set_logs
    ADD CONSTRAINT uix_client_exercise_set_log
        UNIQUE (client_id, plan_day_exercise_id, set_number);

-- Enforce the same validation rules that already exist in the API layer.
ALTER TABLE client_exercise_set_logs
    DROP CONSTRAINT IF EXISTS chk_client_exercise_set_logs_set_number;

ALTER TABLE client_exercise_set_logs
    ADD CONSTRAINT chk_client_exercise_set_logs_set_number
        CHECK (set_number BETWEEN 1 AND 15);

ALTER TABLE client_exercise_set_logs
    DROP CONSTRAINT IF EXISTS chk_client_exercise_set_logs_weight_kg;

ALTER TABLE client_exercise_set_logs
    ADD CONSTRAINT chk_client_exercise_set_logs_weight_kg
        CHECK (weight_kg IS NULL OR weight_kg >= 0);

ALTER TABLE client_exercise_set_logs
    DROP CONSTRAINT IF EXISTS chk_client_exercise_set_logs_reps_done;

ALTER TABLE client_exercise_set_logs
    ADD CONSTRAINT chk_client_exercise_set_logs_reps_done
        CHECK (reps_done IS NULL OR reps_done BETWEEN 0 AND 100);

CREATE INDEX IF NOT EXISTS ix_client_exercise_set_logs_logged_at
    ON client_exercise_set_logs (logged_at);

-- ---------------------------------------------------------------------------
-- 2. TRAINER_SETTINGS
-- ---------------------------------------------------------------------------

-- Keep the column size aligned with the SQLModel definition without risking
-- truncation of existing data.
ALTER TABLE trainer_settings
    ALTER COLUMN logo_public_id TYPE VARCHAR(500);

-- Keep this table on the same date-only convention used elsewhere in the app.
ALTER TABLE trainer_settings
    ALTER COLUMN created_at TYPE DATE USING created_at::date;

ALTER TABLE trainer_settings
    ALTER COLUMN updated_at TYPE DATE USING updated_at::date;
