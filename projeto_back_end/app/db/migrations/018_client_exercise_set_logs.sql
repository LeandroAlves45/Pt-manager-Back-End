-- ============================================================================
-- Migration 018: client exercise set logs
-- ============================================================================
--
-- Creates the table that stores the client's actual performance per set for a
-- planned exercise. This allows the app to persist what the client really did
-- during execution, such as the weight used, reps completed, and any notes.
--
-- Uniqueness is enforced per client + planned exercise + set number so the
-- same set cannot be logged twice for the same client workout context.
-- ============================================================================

CREATE TABLE IF NOT EXISTS client_exercise_set_logs (
    -- Primary key for each logged set entry
    id VARCHAR(36) PRIMARY KEY,

    -- Client who performed the set
    client_id VARCHAR(36) NOT NULL REFERENCES clients(id),

    -- Planned exercise instance inside a specific training plan day
    plan_day_exercise_id VARCHAR(36) NOT NULL REFERENCES plan_day_exercises(id),

    -- Set number inside the exercise prescription (for example: set 1, 2, 3...)
    set_number INTEGER NOT NULL,

    -- Actual load used by the client for this set
    weight_kg FLOAT NULL,

    -- Actual reps completed by the client for this set
    reps_done INTEGER NULL,

    -- Optional free-text notes about execution, effort, pain, etc.
    notes TEXT NULL,

    -- Date when the set performance was logged
    logged_at DATE NOT NULL,

    -- Date of the last update to this log entry
    updated_at DATE NOT NULL,

    -- Prevent duplicate logs for the same client, exercise, and set number
    CONSTRAINT uix_client_exercise_set_log UNIQUE (client_id, plan_day_exercise_id, set_number),

    -- Keep database-level validation aligned with the API and ORM rules
    CONSTRAINT chk_client_exercise_set_logs_set_number CHECK (set_number BETWEEN 1 AND 15),
    CONSTRAINT chk_client_exercise_set_logs_weight_kg CHECK (weight_kg IS NULL OR weight_kg >= 0),
    CONSTRAINT chk_client_exercise_set_logs_reps_done CHECK (reps_done IS NULL OR reps_done BETWEEN 0 AND 100)
);

-- Supports lookups by client, such as listing all logged sets for a client
CREATE INDEX IF NOT EXISTS ix_client_exercise_set_logs_client_id
    ON client_exercise_set_logs (client_id);

-- Supports lookups by planned exercise, such as fetching all logs for an exercise block
CREATE INDEX IF NOT EXISTS ix_client_exercise_set_logs_plan_day_exercise_id
    ON client_exercise_set_logs (plan_day_exercise_id);

-- Supports filtering and ordering by the logging date
CREATE INDEX IF NOT EXISTS ix_client_exercise_set_logs_logged_at
    ON client_exercise_set_logs (logged_at);
