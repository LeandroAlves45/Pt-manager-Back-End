-- Migration 015: align meal_plans column names with ORM model
--
-- IDENTIFIED PROBLEM:
--   Migration 001 created meal_plans with column names different from the ORM model.
--   SQLAlchemy uses the model's names for INSERT — when they differ from the DB,
--   meal_plan INSERTs fail. The meal_plan.id stays in memory but is not saved to the DB.
--   When meal_plan_meal tries to insert with FK to this ID → FK error.
--
--   MISMATCH:
--     DB (001)           →  ORM (Python model)
--     start_date         →  starts_date
--     end_date           →  ends_date
--     protein_target_g   →  protein_target
--     carbs_target_g     →  carbs_target
--     fat_target_g       →  fats_target    (fat → fats)
--
--   SYMPTOM: "Key (meal_id)=(...) is not present in table meal_plan_meals"
--   ROOT CAUSE: meal_plan INSERT fails due to missing column → id not saved in DB
--               → FK in meal_plan_meal points to non-existent ID → FK error
--
-- IDEMPOTENT: uses DO $$ blocks to check column existence before renaming.

DO $$
BEGIN
    -- 1. DATES
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'meal_plans' AND column_name = 'start_date'
    ) THEN
        ALTER TABLE meal_plans RENAME COLUMN start_date TO starts_date;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'meal_plans' AND column_name = 'end_date'
    ) THEN
        ALTER TABLE meal_plans RENAME COLUMN end_date TO ends_date;
    END IF;

    -- 2. MACRO TARGETS
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'meal_plans' AND column_name = 'protein_target_g'
    ) THEN
        ALTER TABLE meal_plans RENAME COLUMN protein_target_g TO protein_target;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'meal_plans' AND column_name = 'carbs_target_g'
    ) THEN
        ALTER TABLE meal_plans RENAME COLUMN carbs_target_g TO carbs_target;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'meal_plans' AND column_name = 'fat_target_g'
    ) THEN
        ALTER TABLE meal_plans RENAME COLUMN fat_target_g TO fats_target;
    END IF;
END $$;

-- 3. RECREATE INDEXES (if they exist with old names)
DROP INDEX IF EXISTS idx_meal_plans_start_date;
DROP INDEX IF EXISTS idx_meal_plans_end_date;

CREATE INDEX IF NOT EXISTS idx_meal_plans_starts_date ON meal_plans (starts_date);
CREATE INDEX IF NOT EXISTS idx_meal_plans_ends_date   ON meal_plans (ends_date);
