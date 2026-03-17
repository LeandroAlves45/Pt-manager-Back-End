-- Migration 005: Avaliações Físicas + Sistema de Alimentação
-- =============================================================================
--
-- Este script é IDEMPOTENTE — pode ser executado múltiplas vezes sem erro.
-- Todos os comandos usam IF NOT EXISTS / IF EXISTS.
--
-- Executado automaticamente pelo migrate.py no startup da aplicação.
-- Não é necessário correr manualmente no DBeaver (mas pode fazê-lo para verificar).
--
-- Ordem de criação respeita as Foreign Keys:
--   1. assessments (depende de clients)
--   2. assessment_measurements (depende de assessments)
--   3. assessment_photos (depende de assessments)
--   4. foods (independente)
--   5. meal_plans (depende de clients)
--   6. meal_plan_meals (depende de meal_plans)
--   7. meal_plan_items (depende de meal_plan_meals + foods)
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. AVALIAÇÕES — registo principal
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assessments (
    id            VARCHAR      PRIMARY KEY,
    client_id     VARCHAR      NOT NULL REFERENCES clients(id),

    weight        FLOAT        NOT NULL CHECK (weight >= 20 AND weight <= 400),
    body_fat      FLOAT                 CHECK (body_fat >= 0 AND body_fat <= 100),
    notes         TEXT,

    -- Questionário como JSONB: flexível, sem colunas fixas.
    -- Permite adicionar novas perguntas sem alterar o schema.
    questionnaire JSONB,

    archived_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assessments_client_id
    ON assessments (client_id);

CREATE INDEX IF NOT EXISTS idx_assessments_created_at
    ON assessments (created_at DESC);

-- Índice parcial: queries de avaliações ativas são as mais comuns
CREATE INDEX IF NOT EXISTS idx_assessments_active
    ON assessments (client_id)
    WHERE archived_at IS NULL;


-- -----------------------------------------------------------------------------
-- 2. AVALIAÇÕES — perímetros corporais (estrutura chave-valor)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assessment_measurements (
    id                VARCHAR     PRIMARY KEY,
    assessment_id     VARCHAR     NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,

    -- Tipo de medição: 'waist', 'hip', 'chest', 'thigh', 'arm', etc.
    -- Chave-valor em vez de colunas fixas: novos tipos não requerem migration.
    measurement_type  VARCHAR(50) NOT NULL,
    value_cm          FLOAT       NOT NULL CHECK (value_cm >= 0 AND value_cm <= 300),

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Um tipo de medição por avaliação (sem duplicados)
    CONSTRAINT uix_assessment_measurement_type
        UNIQUE (assessment_id, measurement_type)
);

CREATE INDEX IF NOT EXISTS idx_measurements_assessment_id
    ON assessment_measurements (assessment_id);


-- -----------------------------------------------------------------------------
-- 3. AVALIAÇÕES — fotos (apenas URLs, binário em serviço externo)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assessment_photos (
    id            VARCHAR      PRIMARY KEY,
    assessment_id VARCHAR      NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,

    -- Valores aceites: front | side | back
    photo_type    VARCHAR(20)  NOT NULL CHECK (photo_type IN ('front', 'side', 'back')),

    -- URL completa no serviço de armazenamento externo (ex: Cloudinary, S3)
    url           VARCHAR(1000) NOT NULL,

    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_photos_assessment_id
    ON assessment_photos (assessment_id);


-- -----------------------------------------------------------------------------
-- 4. CATÁLOGO DE ALIMENTOS
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS foods (
    id         VARCHAR      PRIMARY KEY,
    name       VARCHAR(200) NOT NULL,

    -- Macronutrientes por 100g
    protein    NUMERIC(6,2) NOT NULL CHECK (protein >= 0 AND protein <= 100),
    carbs      NUMERIC(6,2) NOT NULL CHECK (carbs >= 0 AND carbs <= 100),
    fat        NUMERIC(6,2) NOT NULL CHECK (fat >= 0 AND fat <= 100),

    -- GENERATED ALWAYS AS: calculado e armazenado automaticamente pela BD.
    -- Requer PostgreSQL 12+ (Railway usa PostgreSQL 15 por defeito).
    -- NUNCA incluir 'kcal' num INSERT — a BD recusa.
    kcal       NUMERIC(6,2) GENERATED ALWAYS AS
                   ((protein * 4) + (carbs * 4) + (fat * 9)) STORED,

    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_foods_name
    ON foods (name);

CREATE INDEX IF NOT EXISTS idx_foods_is_active
    ON foods (is_active);


-- -----------------------------------------------------------------------------
-- 5. PLANOS ALIMENTARES — cabeçalho
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meal_plans (
    id          VARCHAR      PRIMARY KEY,
    client_id   VARCHAR      NOT NULL REFERENCES clients(id),
    name        VARCHAR(200) NOT NULL,

    -- Tipo de dia: training_day | rest_day | upper_body_day |
    --              lower_body_day | refeed | competition | custom
    -- VARCHAR em vez de ENUM: alterar um ENUM em PostgreSQL requer migration complexa.
    plan_type   VARCHAR(50),

    start_date  DATE,
    end_date    DATE,

    -- Múltiplos planos podem estar ativos (um por plan_type).
    -- Unicidade (client + plan_type ativo) aplicada na camada de aplicação.
    active      BOOLEAN      NOT NULL DEFAULT TRUE,

    notes       TEXT,

    -- Targets de macros definidos pelo PT após cálculo.
    -- Opcionais: podem ser preenchidos na criação ou via PATCH depois.
    kcal_target       FLOAT,
    protein_target_g  FLOAT,
    carbs_target_g    FLOAT,
    fat_target_g      FLOAT,

    archived_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_meal_plan_dates
        CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);

CREATE INDEX IF NOT EXISTS idx_meal_plans_client_id
    ON meal_plans (client_id);

CREATE INDEX IF NOT EXISTS idx_meal_plans_plan_type
    ON meal_plans (plan_type);

-- Índice composto para a query mais comum: "plano ativo de X tipo para Y cliente"
CREATE INDEX IF NOT EXISTS idx_meal_plans_client_type_active
    ON meal_plans (client_id, plan_type, active)
    WHERE archived_at IS NULL;


-- -----------------------------------------------------------------------------
-- 6. PLANOS ALIMENTARES — refeições
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meal_plan_meals (
    id           VARCHAR      PRIMARY KEY,
    meal_plan_id VARCHAR      NOT NULL REFERENCES meal_plans(id) ON DELETE CASCADE,

    -- Ex: 'Pequeno-Almoço', 'Almoço', 'Lanche', 'Jantar', 'Pré-Treino'
    name         VARCHAR(100) NOT NULL,

    -- Ordem de exibição dentro do plano (0 = primeiro)
    order_index  INT          NOT NULL DEFAULT 0 CHECK (order_index >= 0),

    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_meal_plan_meals_plan_id
    ON meal_plan_meals (meal_plan_id);


-- -----------------------------------------------------------------------------
-- 7. PLANOS ALIMENTARES — alimentos por refeição
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meal_plan_items (
    id             VARCHAR      PRIMARY KEY,
    meal_id        VARCHAR      NOT NULL REFERENCES meal_plan_meals(id) ON DELETE CASCADE,
    food_id        VARCHAR      NOT NULL REFERENCES foods(id),

    -- Quantidade em gramas para esta refeição.
    -- Macros calculados dinamicamente: (food.macro / 100) * quantity_grams
    -- NUNCA armazenados aqui.
    quantity_grams NUMERIC(7,2) NOT NULL CHECK (quantity_grams > 0 AND quantity_grams <= 5000),

    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_meal_plan_items_meal_id
    ON meal_plan_items (meal_id);

CREATE INDEX IF NOT EXISTS idx_meal_plan_items_food_id
    ON meal_plan_items (food_id);


-- =============================================================================
-- FIM DA MIGRATION 001
-- =============================================================================