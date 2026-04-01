-- =============================================================================
-- Migration 011: Cleanup of incorrect demo data
-- =============================================================================
--
-- Context:
--   The demo seed partially failed in previous sessions, leaving
--   inconsistent records. This migration removes everything safely,
--   respecting FK constraint order.
--
-- Target emails:
--   trainer@demo.pt  (DEFAULT_TRAINER_EMAIL)
--   cliente@demo.pt  (DEFAULT_CLIENT_EMAIL)
--
-- Idempotent: DELETE on empty tables is a no-op.
--
-- Fixes compared to the previous version:
--   "check_ins"   → "checkins"           (actual table name in ORM)
--   "assessments" → "initial_assessments" (actual table name in ORM)
--   Added: pack_consumptions before sessions (FK constraint)
--   Added: plan_exercise_set_loads, plan_day_exercises, training_plan_days
--          before training_plans (cascading FK chain)
--   Added: meal_plan_items, meal_plan_meals before meal_plans
-- =============================================================================
 
-- Step 1: active_tokens for demo users
-- (FK active_tokens.user_id → users.id)
DELETE FROM active_tokens
WHERE user_id IN (
    SELECT id FROM users
    WHERE email IN ('trainer@demo.pt', 'cliente@demo.pt')
);
 
-- Step 2: checkins requested by the demo trainer
-- CORRECT NAME: "checkins" (not "check_ins")
-- (FK checkins.requested_by_trainer_id → users.id)
DELETE FROM checkins
WHERE requested_by_trainer_id IN (
    SELECT id FROM users WHERE email = 'trainer@demo.pt'
);
 
-- Step 3: all records referencing the demo client
-- Must be deleted BEFORE deleting from the clients table
 
DELETE FROM client_supplements
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');
 
DELETE FROM checkins
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');
 
DELETE FROM client_active_plans
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');
 
DELETE FROM client_packs
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');
 
-- pack_consumptions references sessions.id — delete before sessions
DELETE FROM pack_consumptions
WHERE session_id IN (
    SELECT id FROM sessions
    WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt')
);
 
DELETE FROM sessions
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');
 
-- training_plans has cascading children — delete from leaf to root
DELETE FROM plan_exercise_set_loads
WHERE plan_day_exercise_id IN (
    SELECT pde.id FROM plan_day_exercises pde
    JOIN training_plan_days tpd ON pde.plan_day_id = tpd.id
    JOIN training_plans tp ON tpd.plan_id = tp.id
    WHERE tp.client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt')
);
 
DELETE FROM plan_day_exercises
WHERE plan_day_id IN (
    SELECT tpd.id FROM training_plan_days tpd
    JOIN training_plans tp ON tpd.plan_id = tp.id
    WHERE tp.client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt')
);
 
DELETE FROM training_plan_days
WHERE plan_id IN (
    SELECT id FROM training_plans
    WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt')
);
 
DELETE FROM training_plans
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');
 
-- meal_plans has cascading children — delete from leaf to root
DELETE FROM meal_plan_items
WHERE meal_id IN (
    SELECT mpm.id FROM meal_plan_meals mpm
    JOIN meal_plans mp ON mpm.meal_plan_id = mp.id
    WHERE mp.client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt')
);
 
DELETE FROM meal_plan_meals
WHERE meal_plan_id IN (
    SELECT id FROM meal_plans
    WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt')
);
 
DELETE FROM meal_plans
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');
 
-- CORRECT NAME: "initial_assessments" (not "assessments")
DELETE FROM initial_assessments
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');
 
-- Nullify users.client_id before deleting the Client record
-- (FK users.client_id → clients.id)
UPDATE users
SET client_id = NULL
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');
 
-- Step 4: Client record
DELETE FROM clients
WHERE email = 'cliente@demo.pt';
 
-- Step 5: TrainerSettings
DELETE FROM trainer_settings
WHERE trainer_user_id IN (
    SELECT id FROM users WHERE email = 'trainer@demo.pt'
);
 
-- Step 6: TrainerSubscription
DELETE FROM trainer_subscriptions
WHERE trainer_user_id IN (
    SELECT id FROM users WHERE email = 'trainer@demo.pt'
);
 
-- Step 7: Users — last because all others reference users.id
DELETE FROM users
WHERE email IN ('trainer@demo.pt', 'cliente@demo.pt');