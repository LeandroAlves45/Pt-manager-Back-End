-- =============================================================================
-- Migration 004: Exempt billing, sessions multi-tenancy, trainer settings
-- =============================================================================
--
-- Esta migração é IDEMPOTENTE — segura de executar múltiplas vezes.
-- Todas as instruções usam IF NOT EXISTS / IF EXISTS.
-- Executada automaticamente no arranque do container via migrate.py.
--
-- Alterações:
--   1. users: adiciona is_exempt_from_billing (free-forever trainer model)
--   2. sessions: adiciona owner_trainer_id (correcção B-08 — isolamento multi-tenant)
--   3. trainer_settings: nova tabela (white-label branding por trainer)
-- =============================================================================
 
 
-- -----------------------------------------------------------------------------
-- 1. USERS: coluna is_exempt_from_billing
--
-- Trainers com este campo a TRUE contornam TODAS as verificações de subscrição.
-- Equivale a ter sempre uma subscrição PRO activa, sem Stripe.
-- Apenas superusers podem alterar este valor via API.
-- DEFAULT FALSE garante que todos os trainers existentes ficam sujeitos
-- às verificações normais de subscrição após esta migração.
-- -----------------------------------------------------------------------------
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_exempt_from_billing BOOLEAN NOT NULL DEFAULT FALSE;
 
-- Índice parcial: apenas indexa as linhas onde o campo é TRUE.
-- Optimização para o require_active_subscription dependency que verifica
-- este campo em cada pedido autenticado de trainer.
CREATE INDEX IF NOT EXISTS idx_users_exempt_billing
    ON users (is_exempt_from_billing)
    WHERE is_exempt_from_billing = TRUE;
 
 
-- -----------------------------------------------------------------------------
-- 2. SESSIONS: coluna owner_trainer_id
--
-- Correcção do bug B-08: sem este campo, qualquer trainer autenticado podia
-- aceder a sessões de outro trainer se conhecesse o session ID.
-- Após esta migração, todos os routers de sessões devem filtrar por
-- owner_trainer_id = current_user.id (além do client_id).
--
-- ON DELETE SET NULL: se o trainer for eliminado, as sessões ficam órfãs
-- mas não são eliminadas — preserva histórico.
-- -----------------------------------------------------------------------------
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS owner_trainer_id VARCHAR REFERENCES users(id) ON DELETE SET NULL;
 
-- Índice para queries de listagem de sessões por trainer (rota GET /sessions)
CREATE INDEX IF NOT EXISTS idx_sessions_owner_trainer_id
    ON sessions (owner_trainer_id)
    WHERE owner_trainer_id IS NOT NULL;
 
 
-- -----------------------------------------------------------------------------
-- 3. TRAINER_SETTINGS: nova tabela para white-label branding
--
-- Cada trainer personaliza a app com o seu logo e cor primária.
-- Esta tabela centraliza essas preferências.
--
-- primary_color: valor hex da cor primária (ex: "#1A7A4A")
--   O frontend converte este valor para HSL e injeta nas CSS variables
--   do documento no momento do login — sem rebuild necessário.
--
-- logo_url: duplicado de users.logo_url para performance — o endpoint
--   de branding lê daqui sem fazer JOIN com a tabela users.
--
-- app_name: nome personalizado do trainer visível na sidebar e no
--   título do browser.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trainer_settings (
    id              VARCHAR         PRIMARY KEY,
    trainer_user_id VARCHAR         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Garante que cada trainer tem apenas um registo de settings (relação 1:1)
    UNIQUE (trainer_user_id),
 
    -- Branding
    primary_color   VARCHAR(7)      NOT NULL DEFAULT '#00A8E8',  -- hex incluindo '#'
    logo_url        VARCHAR(500),                                 -- Cloudinary secure_url
    logo_public_id  VARCHAR(200),                                 -- Cloudinary public_id (para deleção futura)
 
    -- Preferências da app
    app_name        VARCHAR(100)    NOT NULL DEFAULT 'PT Manager',
    timezone        VARCHAR(50)     NOT NULL DEFAULT 'Europe/Lisbon',
 
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
 
-- Índice único já coberto pelo UNIQUE constraint acima.
-- Índice adicional para lookup por trainer_user_id em queries de branding.
CREATE INDEX IF NOT EXISTS idx_trainer_settings_trainer_user_id
    ON trainer_settings (trainer_user_id);