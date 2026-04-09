-- Migration 016: rename foods.fat → foods.fats to match ORM model
--
-- MISMATCH:
--   Migration 001 created:  fat NUMERIC(6,2)
--   ORM model Food has:     fats: float
--
-- IMPACT of mismatch:
--   - SELECT: food.fats = None (column 'fat' not mapped to 'fats' attribute)
--             → macro calculations show 0 for fats (wrong caloric totals)
--   - INSERT (create_food endpoint): ProgrammingError — column "fats" does not exist
--
-- GENERATED COLUMN DEPENDENCY:
--   kcal is GENERATED ALWAYS AS ((protein * 4) + (carbs * 4) + (fat * 9))
--   Renaming fat requires: drop kcal, rename fat→fats, recreate kcal with new formula.
--
-- IDEMPOTENT: checks column existence before any ALTER.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'foods' AND column_name = 'fat'
    ) THEN
        -- 1. Drop the generated column (depends on 'fat')
        ALTER TABLE foods DROP COLUMN IF EXISTS kcal;

        -- 2. Rename the base column
        ALTER TABLE foods RENAME COLUMN fat TO fats;

        -- 3. Re-add kcal as GENERATED using the new column name
        ALTER TABLE foods ADD COLUMN kcal NUMERIC(6,2)
            GENERATED ALWAYS AS ((protein * 4) + (carbs * 4) + (fats * 9)) STORED;
    END IF;
END $$;
