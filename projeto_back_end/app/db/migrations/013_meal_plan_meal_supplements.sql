-- Migration 014: association table between meals and supplements (NR-04)
--
-- Business reason:
--   The trainer wants to specify which supplements the client should take
--   with each specific meal in the meal plan.
--   E.g.: Meal 1 (breakfast) → Omega-3, Vitamin D
--         Meal 3 (pre-workout) → Creatine, Caffeine
--
-- Design decisions:
--   - FK to meal_plan_meals with ON DELETE CASCADE:
--     when removing a meal (delete-and-replace), the supplement
--     associations are automatically removed — no orphans.
--   - FK to supplements without CASCADE: we don't want to remove associations
--     if a supplement is archived — history should be preserved.
--   - UNIQUE(meal_plan_meal_id, supplement_id): a supplement can only
--     appear once per meal.
--   - notes is optional: allows free text such as "Take with 300ml of water".
 
CREATE TABLE IF NOT EXISTS meal_plan_meal_supplements (
    id                  VARCHAR     PRIMARY KEY DEFAULT gen_random_uuid()::varchar,
    meal_plan_meal_id   VARCHAR     NOT NULL REFERENCES meal_plan_meals(id) ON DELETE CASCADE,
    supplement_id       VARCHAR     NOT NULL REFERENCES supplements(id),
    notes               VARCHAR(300),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 
    CONSTRAINT uq_meal_supplement UNIQUE (meal_plan_meal_id, supplement_id)
);
 
CREATE INDEX IF NOT EXISTS idx_meal_plan_meal_supplements_meal_id
    ON meal_plan_meal_supplements (meal_plan_meal_id);
 
CREATE INDEX IF NOT EXISTS idx_meal_plan_meal_supplements_supplement_id
    ON meal_plan_meal_supplements (supplement_id);
 
COMMENT ON TABLE meal_plan_meal_supplements IS
    'Association between meal plan meals and supplements.';