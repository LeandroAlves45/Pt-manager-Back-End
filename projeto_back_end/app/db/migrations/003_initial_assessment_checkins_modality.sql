-- Migration 003: Initial Assessments, Check-Ins e modalidade de treino
-- =============================================================================
-- IDEMPOTENTE — pode ser executado múltiplas vezes sem erro.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. CLIENTS — adicionar modalidade de treino e data de avaliação
-- -----------------------------------------------------------------------------

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS training_modality VARCHAR(20)
        NOT NULL DEFAULT 'presencial'
        CHECK (training_modality IN ('presencial', 'online'));

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS next_assessment_date DATE;

CREATE INDEX IF NOT EXISTS idx_clients_training_modality
    ON clients (training_modality);


-- -----------------------------------------------------------------------------
-- 2. INITIAL_ASSESSMENTS — avaliação inicial de saúde
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS initial_assessments (
    id                      VARCHAR      PRIMARY KEY,
    client_id               VARCHAR      NOT NULL REFERENCES clients(id),
    assessed_by_trainer_id  VARCHAR      NOT NULL REFERENCES users(id),

    weight_kg               FLOAT        CHECK (weight_kg >= 20 AND weight_kg <= 400),
    height_cm               INTEGER      CHECK (height_cm >= 80 AND height_cm <= 260),
    body_fat                FLOAT        CHECK (body_fat >= 0 AND body_fat <= 100),

    -- Questionário de saúde completo como JSONB
    health_questionnaire    JSONB,

    notes                   TEXT,

    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_initial_assessments_client_id
    ON initial_assessments (client_id);

CREATE INDEX IF NOT EXISTS idx_initial_assessments_created_at
    ON initial_assessments (created_at DESC);


-- -----------------------------------------------------------------------------
-- 3. CHECK_INS — check-ins periódicos de progresso
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS check_ins (
    id                          VARCHAR     PRIMARY KEY,
    client_id                   VARCHAR     NOT NULL REFERENCES clients(id),
    requested_by_trainer_id     VARCHAR     NOT NULL REFERENCES users(id),

    -- Estado: pending | completed | skipped
    status                      VARCHAR(20) NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending', 'completed', 'skipped')),

    -- Dados preenchidos pelo cliente
    weight_kg                   FLOAT       CHECK (weight_kg >= 20 AND weight_kg <= 400),
    body_fat                    FLOAT       CHECK (body_fat >= 0 AND body_fat <= 100),

    -- Questionário periódico como JSONB
    questionnaire               JSONB,

    -- Fotos de progresso como JSONB: [{"type": "frontal", "url": "..."}]
    photos                      JSONB,

    client_notes                TEXT,
    trainer_notes               TEXT,

    requested_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at                TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_check_ins_client_id
    ON check_ins (client_id);

CREATE INDEX IF NOT EXISTS idx_check_ins_status
    ON check_ins (status);

-- Índice composto para a query mais comum:
-- "check-ins pendentes do cliente X" (dashboard do cliente)
CREATE INDEX IF NOT EXISTS idx_check_ins_client_pending
    ON check_ins (client_id, status)
    WHERE status = 'pending';

-- Adicionar logo_url à tabela users
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS logo_url VARCHAR(500);