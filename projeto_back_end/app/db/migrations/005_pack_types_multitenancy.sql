-- =============================================================================
-- Migration 005: Pack types multi-tenancy
-- =============================================================================
--
-- Esta migração é IDEMPOTENTE — segura de executar múltiplas vezes.
-- Todas as instruções usam IF NOT EXISTS.
--
-- Alterações:
--   1. pack_types: adiciona owner_trainer_id (isolamento multi-tenant)
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. PACK_TYPES: coluna owner_trainer_id
--
-- Cada pack type pertence a um trainer específico.
-- NULL nos registos existentes (packs globais/legados).
-- ON DELETE SET NULL: se o trainer for eliminado, os pack types ficam órfãos
-- mas não são eliminados — preserva histórico.
-- -----------------------------------------------------------------------------
ALTER TABLE pack_types
    ADD COLUMN IF NOT EXISTS owner_trainer_id VARCHAR REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_pack_types_owner_trainer_id
    ON pack_types (owner_trainer_id)
    WHERE owner_trainer_id IS NOT NULL;
