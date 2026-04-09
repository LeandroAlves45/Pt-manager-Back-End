-- Migration 017: fix meal_plan_items FK referencing wrong table
--
-- ROOT CAUSE:
--   The FK constraint on meal_plan_items.meal_id references table
--   "meal_plans_meal" (wrong), but the ORM model MealPlanMeal uses
--   __tablename__ = "meal_plan_meals" (correct).
--
--   This happened because SQLModel.metadata.create_all() ran at startup
--   while an older version of the ORM model existed (different __tablename__).
--   Migration 001 was then skipped for meal_plan_items (IF NOT EXISTS),
--   leaving the broken FK in place.
--
-- SYMPTOM:
--   insert or update on table "meal_plan_items" violates foreign key
--   constraint "meal_plan_items_meal_id_fkey"
--   Key (meal_id)=(...) is not present in table "meal_plans_meal"
--
-- FIX:
--   1. Drop the broken FK and recreate it pointing to meal_plan_meals(id).
--   2. Drop the orphaned "meal_plans_meal" table if it exists and is empty.
--
-- IDEMPOTENT: all changes are conditional on current DB state.

-- Step 1: fix the FK constraint
DO $$
DECLARE
    fk_constraint_name  TEXT;
    fk_referenced_table TEXT;
BEGIN
    -- Find the FK on meal_plan_items.meal_id and which table it references
    SELECT tc.constraint_name, ccu.table_name
    INTO fk_constraint_name, fk_referenced_table
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name
       AND tc.table_schema = kcu.table_schema
    JOIN information_schema.referential_constraints rc
        ON tc.constraint_name = rc.constraint_name
    JOIN information_schema.key_column_usage ccu
        ON rc.unique_constraint_name = ccu.constraint_name
       AND rc.unique_constraint_schema = ccu.table_schema
    WHERE tc.table_name = 'meal_plan_items'
      AND tc.constraint_type = 'FOREIGN KEY'
      AND kcu.column_name = 'meal_id'
    LIMIT 1;

    IF fk_referenced_table IS NOT NULL AND fk_referenced_table != 'meal_plan_meals' THEN
        RAISE NOTICE 'FK meal_plan_items.meal_id references "%", fixing to meal_plan_meals...', fk_referenced_table;

        EXECUTE format('ALTER TABLE meal_plan_items DROP CONSTRAINT %I', fk_constraint_name);

        ALTER TABLE meal_plan_items
            ADD CONSTRAINT meal_plan_items_meal_id_fkey
            FOREIGN KEY (meal_id) REFERENCES meal_plan_meals(id) ON DELETE CASCADE;

        RAISE NOTICE 'FK fixed: meal_plan_items.meal_id now references meal_plan_meals';
    ELSE
        RAISE NOTICE 'FK meal_plan_items.meal_id already references meal_plan_meals — no action needed';
    END IF;
END $$;

-- Step 2: drop the orphaned table (uses EXECUTE to avoid parse-time errors)
DO $$
DECLARE
    has_data BOOLEAN := FALSE;
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'meal_plans_meal'
    ) THEN
        EXECUTE 'SELECT EXISTS(SELECT 1 FROM meal_plans_meal LIMIT 1)' INTO has_data;

        IF NOT has_data THEN
            EXECUTE 'DROP TABLE meal_plans_meal';
            RAISE NOTICE 'Dropped orphaned empty table meal_plans_meal';
        ELSE
            RAISE WARNING 'Table meal_plans_meal still has data — not dropped automatically. Manual cleanup required.';
        END IF;
    END IF;
END $$;
