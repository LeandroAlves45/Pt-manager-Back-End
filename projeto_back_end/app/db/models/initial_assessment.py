"""
Avaliação inicial do cliente — formulário de saúde completo.

Preenchido pelo trainer na primeira consulta com o cliente.
Campos baseados no formulário de intake padrão (historial médico,
objetivos, hábitos, etc.).

Diferença de CheckIn:
  - InitialAssessment: feito uma vez (ou raramente), pelo trainer, 
    com historial médico completo
  - CheckIn: feito periodicamente, pode ser preenchido pelo cliente,
    com dados de progresso
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Column, DateTime
from sqlmodel import SQLModel, Field
from sqlalchemy.dialects.postgresql import JSONB
from app.utils.time import utc_now_datetime


class InitialAssessment(SQLModel, table=True):
    __tablename__ = "initial_assessments"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    # FK para cliente
    client_id: str = Field(foreign_key="clients.id", index=True)

    # Quem fez a avaliação (o trainer)
    assessed_by_trainer_id: str = Field(foreign_key="users.id", index=True)

    # --------------------------------------------------
    # Dados biométricos recolhidos na avaliação inicial
    # --------------------------------------------------
    weight_kg: Optional[float] = Field(default=None, ge=20.0, le=400.0)
    height_cm: Optional[int] = Field(default=None, ge=80, le=260)
    body_fat: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    # --------------------------------------------------
    # Questionário de saúde e historial — armazenado como JSONB
    # Estrutura esperada do dict (todos opcionais):
    #
    # SECÇÃO 1 — IDENTIFICAÇÃO
    #   occupation: str           — profissão (ex: "professor", "escritório")
    #   activity_level: str       — sedentário | levemente ativo | moderadamente ativo | muito ativo
    #
    # SECÇÃO 2 — HISTORIAL DE SAÚDE
    #   medical_conditions: str   — doenças diagnosticadas (diabetes, hipertensão, etc.)
    #   medications: str          — medicação atual
    #   injuries: str             — lesões passadas ou atuais
    #   surgeries: str            — cirurgias relevantes
    #   family_history: str       — historial familiar relevante
    #
    # SECÇÃO 3 — HÁBITOS DE VIDA
    #   sleep_hours: float        — horas de sono por noite
    #   sleep_quality: str        — boa | razoável | má
    #   stress_level: int         — 1 a 5
    #   smoking: bool             — fumador
    #   alcohol: str              — nunca | ocasional | frequente
    #   water_intake_l: float     — litros de água por dia
    #
    # SECÇÃO 4 — HISTORIAL DESPORTIVO
    #   previous_training: str    — experiência de treino anterior
    #   sports_practiced: str     — desportos praticados
    #   training_frequency: int   — dias de treino por semana (atual)
    #
    # SECÇÃO 5 — OBJETIVOS
    #   primary_goal: str         — perda de peso | ganho muscular | manutenção | saúde | performance
    #   secondary_goals: str      — objetivos secundários
    #   target_weight: float      — peso objetivo (kg)
    #   deadline_months: int      — prazo em meses
    #
    # SECÇÃO 6 — ALIMENTAÇÃO
    #   dietary_restrictions: str — intolerâncias, alergias, preferências
    #   meal_frequency: int       — número de refeições por dia
    #   supplements_current: str  — suplementação atual
    #
    # SECÇÃO 7 — PREFERÊNCIAS DE TREINO
    #   preferred_schedule: str   — manhã | tarde | noite
    #   gym_access: bool          — tem acesso a ginásio
    #   equipment_available: str  — equipamento disponível
    #   limitations: str          — limitações físicas para o treino
    # --------------------------------------------------
    health_questionnaire: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True)
    )

    notes: Optional[str] = Field(default=None, max_length=1000)

    created_at: datetime = Field(
        default_factory=utc_now_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utc_now_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )