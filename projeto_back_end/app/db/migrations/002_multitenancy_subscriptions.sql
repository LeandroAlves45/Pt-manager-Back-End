-- Migration 007: Multi-tenancy + Superuser + Subscrições Stripe
-- =============================================================================
--
-- Este script é IDEMPOTENTE — pode ser executado múltiplas vezes sem erro.
--
-- O que esta migration faz:
--   1. Adiciona owner_trainer_id às tabelas de negócio (clientes, planos, etc.)
--   2. Cria a tabela trainer_subscriptions
--   3. Actualiza o CHECK constraint de role na tabela users para incluir "superuser"
--   4. Adiciona índices para as novas colunas
--
-- ATENÇÃO para dados existentes:
--   Os ALTER TABLE ADD COLUMN com DEFAULT NULL não afectam dados existentes.
--   No entanto, as colunas owner_trainer_id ficam NULL nos registos existentes.
--   Deves correr um script de backfill após a migration se tiveres dados em produção.
--
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. USERS — adiciona suporte a role "superuser"
-- -----------------------------------------------------------------------------

-- Recria o check constraint para incluir "superuser"

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;

ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('superuser', 'trainer', 'client'));

-- -----------------------------------------------------------------------------
-- 2. CLIENTS — adiciona owner_trainer_id
-- -----------------------------------------------------------------------------

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS owner_trainer_id VARCHAR REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_clients_owner_trainer_id
    ON clients (owner_trainer_id)
    WHERE owner_trainer_id IS NOT NULL;

-- Índice composto para a query mais comum: "clientes activos deste trainer"
CREATE INDEX IF NOT EXISTS idx_clients_trainer_active
    ON clients (owner_trainer_id, archived_at)
    WHERE archived_at IS NULL;

-- -----------------------------------------------------------------------------
-- 3. TRAINING_PLANS — adiciona owner_trainer_id
-- -----------------------------------------------------------------------------

ALTER TABLE training_plans
    ADD COLUMN IF NOT EXISTS owner_trainer_id VARCHAR REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_training_plans_owner_trainer_id
    ON training_plans (owner_trainer_id)
    WHERE owner_trainer_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 4. EXERCISES — adiciona owner_trainer_id
-- NULL = global (visível a todos)
-- value = privado do trainer
-- -----------------------------------------------------------------------------

ALTER TABLE exercises
    ADD COLUMN IF NOT EXISTS owner_trainer_id VARCHAR REFERENCES users(id) ON DELETE CASCADE;

-- Índice parcial para exercícios globais (query mais comum para todos os trainers)
CREATE INDEX IF NOT EXISTS idx_exercises_global
    ON exercises (name)
    WHERE owner_trainer_id IS NULL;

-- Índice para exercícios privados de um trainer específico
CREATE INDEX IF NOT EXISTS idx_exercises_owner
    ON exercises (owner_trainer_id)
    WHERE owner_trainer_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 5. FOODS — adiciona owner_trainer_id (mesmo padrão dos exercícios)
-- -----------------------------------------------------------------------------

ALTER TABLE foods
    ADD COLUMN IF NOT EXISTS owner_trainer_id VARCHAR REFERENCES users(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_foods_global
    ON foods (name)
    WHERE owner_trainer_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_foods_owner
    ON foods (owner_trainer_id)
    WHERE owner_trainer_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 6. MEAL_PLANS — adiciona owner_trainer_id
-- -----------------------------------------------------------------------------

ALTER TABLE meal_plans
    ADD COLUMN IF NOT EXISTS owner_trainer_id VARCHAR REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_meal_plans_owner_trainer_id
    ON meal_plans (owner_trainer_id)
    WHERE owner_trainer_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- 7. TRAINER_SUBSCRIPTIONS — nova tabela
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS trainer_subscriptions (
    id                      VARCHAR     PRIMARY KEY,

    -- FK para o trainer — unique garante 1 subscrição por trainer
    trainer_user_id         VARCHAR     NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,

    -- Estado da subscrição
    status                  VARCHAR     NOT NULL DEFAULT 'trialing'
                                        CHECK (status IN (
                                            'trialing', 'trial_expired', 'active',
                                            'past_due', 'cancelled'
                                        )),

    -- Tier de preço actual
    tier                    VARCHAR     NOT NULL DEFAULT 'free'
                                        CHECK (tier IN ('free', 'starter', 'pro')),

    -- Datas de trial e billing
    trial_end               TIMESTAMPTZ,
    current_period_start    TIMESTAMPTZ,
    current_period_end      TIMESTAMPTZ,

    -- Referências Stripe
    stripe_customer_id      VARCHAR     UNIQUE,
    stripe_subscription_id  VARCHAR     UNIQUE,
    stripe_price_id         VARCHAR,

    -- Cache de clientes activos (evita COUNT em cada request)
    active_clients_count    INTEGER     NOT NULL DEFAULT 0 CHECK (active_clients_count >= 0),

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índice para busca por stripe_customer_id (usado no webhook handler)
CREATE INDEX IF NOT EXISTS idx_trainer_subs_stripe_customer
    ON trainer_subscriptions (stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

-- Índice para busca por stripe_subscription_id (usado no webhook handler)
CREATE INDEX IF NOT EXISTS idx_trainer_subs_stripe_sub
    ON trainer_subscriptions (stripe_subscription_id)
    WHERE stripe_subscription_id IS NOT NULL;

-- Índice para filtrar por status (dashboard do superuser)
CREATE INDEX IF NOT EXISTS idx_trainer_subs_status
    ON trainer_subscriptions (status);

-- --------------------------------------------------------------------------------
-- 8. SUPPLEMENT — catalogo de suplementos (multi-tenant, igual aos exercícios e alimentos)
-- --------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS supplements (
    id                  VARCHAR     PRIMARY KEY,

    -- Nome do suplemento — ex: "Creatina Monohidratada"
    name                VARCHAR(100) NOT NULL CHECK (LENGTH(name) >= 1),

    -- Descrição do suplemento — benefícios, modo de uso, etc.
    description         VARCHAR(500),

    -- Quantidade por dose — ex: "5g", "1 scoop", "2 cápsulas"
    -- Intencionalmente flexível (string) para suportar diferentes unidades
    serving_size        VARCHAR(50),

    -- Altura em que tomar — ex: "Pós-treino", "Ao acordar", "Antes de dormir"
    timing              VARCHAR(50),

    -- Notas internas do trainer — NÃO visíveis para clientes
    -- Filtradas a nível de endpoint consoante o role do utilizador autenticado
    trainer_notes       TEXT,

    -- Soft delete — o registo é preservado para histórico
    -- NULL = activo, valor = data de arquivamento
    archived_at         TIMESTAMPTZ,

    -- FK para o trainer que criou o suplemento — obrigatório
    -- ON DELETE RESTRICT: impede apagar o trainer enquanto tiver suplementos criados
    created_by_user_id  VARCHAR     NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índice para listagem por nome (ordenação padrão na listagem)
CREATE INDEX IF NOT EXISTS idx_supplements_name
    ON supplements (name);

-- Índice parcial para suplementos activos — a query mais comum
-- Evita varrer registos arquivados nas listagens normais
CREATE INDEX IF NOT EXISTS idx_supplements_active
    ON supplements (name)
    WHERE archived_at IS NULL;

-- Índice para ver os suplementos de um trainer específico
CREATE INDEX IF NOT EXISTS idx_supplements_created_by
    ON supplements (created_by_user_id);

-- Índice composto: "suplementos activos criados por este trainer"
CREATE INDEX IF NOT EXISTS idx_supplements_trainer_active
    ON supplements (created_by_user_id, archived_at)
    WHERE archived_at IS NULL;

