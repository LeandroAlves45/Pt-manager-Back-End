-- =============================================================================
-- Migration 011: Cleanup of incorrect demo data
-- =============================================================================
-- Problem Context:
--   The demo seed partially failed in previous sessions, leaving
--   inconsistent records in the database. Specifically:
--     - Demo trainer/client Users may exist without their dependent records
--       (Client, TrainerSubscription, TrainerSettings, CheckIn)
--     - The Client record may be missing even if the User is already created
--     - Orphaned records in active_tokens and checkins linked to IDs that no
--       longer exist correctly
-- What this migration does:
--   Safely removes ALL demo records, respecting FK order:
--     1. active_tokens (references users.id)
--     2. check_ins (references clients.id and users.id)
--     3. client_supplements (references clients.id)
--     4. clients (references users.id via owner_trainer_id)
--     5. trainer_settings (references users.id)
--     6. trainer_subscriptions (references users.id)
--     7. users (root table)
--   Uses DELETE ... WHERE email IN (...) to identify records.
--   It is idempotent: if records do not exist, DELETE does nothing.
-- ATTENTION: This migration identifies records by the email configured
--   in the DEMO_TRAINER_EMAIL and DEMO_CLIENT_EMAIL variables. The values
--   below correspond to the emails used in the project's development
--   environment. Adjust if your demo emails are different.
--   Target Emails (DEFAULT_TRAINER_EMAIL / DEFAULT_CLIENT_EMAIL variables):
--     trainer@demo.pt
--     cliente@demo.pt
-- =============================================================================

-- Step 1: Delete active_tokens for demo users
-- (must be done before deleting users — FK in active_tokens.user_id)
DELETE FROM active_tokens
WHERE user_id IN (
    SELECT id FROM users
    WHERE email IN ('trainer@demo.pt', 'cliente@demo.pt')
);
 
-- Step 2: Delete check_ins linked to the demo trainer
-- (check_ins.requested_by_trainer_id references users.id)
DELETE FROM check_ins
WHERE requested_by_trainer_id IN (
    SELECT id FROM users WHERE email = 'trainer@demo.pt'
);
 
-- Step 3: Delete ALL records referencing clients for the demo client
-- (must be done before deleting from clients — multiple FKs point to clients.id)

DELETE FROM client_supplements
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');

DELETE FROM checkins
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');

DELETE FROM client_active_plans
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');

DELETE FROM client_packs
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');

DELETE FROM sessions
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');

DELETE FROM training_plans
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');

DELETE FROM assessments
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');

DELETE FROM meal_plans
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');

DELETE FROM initial_assessments
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');

-- Nullify users.client_id that references the demo client
UPDATE users
SET client_id = NULL
WHERE client_id IN (SELECT id FROM clients WHERE email = 'cliente@demo.pt');

-- Step 4: Delete the Client record
DELETE FROM clients
WHERE email = 'cliente@demo.pt';
 
-- Step 5: Delete TrainerSettings for the demo trainer
-- (trainer_settings.trainer_user_id references users.id)
DELETE FROM trainer_settings
WHERE trainer_user_id IN (
    SELECT id FROM users WHERE email = 'trainer@demo.pt'
);
 
-- Step 6: Delete TrainerSubscription for the demo trainer
-- (trainer_subscriptions.trainer_user_id references users.id)
DELETE FROM trainer_subscriptions
WHERE trainer_user_id IN (
    SELECT id FROM users WHERE email = 'trainer@demo.pt'
);
 
-- Step 7: Delete the Users (demo trainer and client)
-- This is the last step because other records reference users.id
DELETE FROM users
WHERE email IN ('trainer@demo.pt', 'cliente@demo.pt');