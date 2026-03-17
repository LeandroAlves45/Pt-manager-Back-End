-- =============================================================================
-- Migration 007: Client Supplements Assignment
-- =============================================================================
--
-- Idempotent — safe to run multiple times (all statements use IF NOT EXISTS).
-- Runs automatically on container startup via migrate.py.
--
-- Purpose:
--   Creates the join table between clients and supplements.
--   A trainer can assign one or more supplements to a client,
--   optionally overriding the default dose and timing, and adding
--   client-specific instructions.
--
-- Multi-tenancy:
--   owner_trainer_id is stored on the assignment record so that
--   list queries can filter by trainer without joining to clients.
--
-- Uniqueness:
--   A supplement can only be assigned once per client.
--   The UNIQUE constraint on (client_id, supplement_id) prevents duplicates
--   and makes the assign operation idempotent via ON CONFLICT.
-- =============================================================================
 
CREATE TABLE IF NOT EXISTS client_supplements (
    id                  VARCHAR         PRIMARY KEY,
 
    -- The client receiving this supplement
    client_id           VARCHAR         NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
 
    -- The supplement being assigned (from the supplements catalogue)
    supplement_id       VARCHAR         NOT NULL REFERENCES supplements(id) ON DELETE CASCADE,
 
    -- Multi-tenancy: which trainer made this assignment
    owner_trainer_id    VARCHAR         NOT NULL REFERENCES users(id),
 
    -- Optional client-specific overrides (can differ from supplement defaults)
    dose                VARCHAR(100),           -- ex: "5g", "1 capsule", "2 scoops"
    timing_notes        VARCHAR(200),           -- ex: "30 min before training"
    notes               TEXT,                   -- free-text trainer instructions for this client
 
    assigned_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
 
    -- Prevent assigning the same supplement twice to the same client
    UNIQUE (client_id, supplement_id)
);
 
-- Fast lookup of all supplements assigned to a specific client
CREATE INDEX IF NOT EXISTS idx_client_supplements_client_id
    ON client_supplements (client_id);
 
-- Fast lookup of all client assignments for a trainer (multi-tenancy filter)
CREATE INDEX IF NOT EXISTS idx_client_supplements_trainer_id
    ON client_supplements (owner_trainer_id);
 
-- Fast lookup by supplement (to find all clients using a given supplement)
CREATE INDEX IF NOT EXISTS idx_client_supplements_supplement_id
    ON client_supplements (supplement_id);