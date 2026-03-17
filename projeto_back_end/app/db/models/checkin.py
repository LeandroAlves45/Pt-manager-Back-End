"""
Check-In periódico de progresso.

Fluxo:
  1. Trainer cria um CheckIn com status="pending" para um cliente
  2. Cliente vê na sua dashboard: "Tens um check-in pendente"
  3. Cliente preenche os dados (peso, questionário, fotos)
  4. Status muda para "completed"
  5. Trainer analisa os dados no painel

Não usa o scheduler de notificações — o alerta é visual na app,
não por email.
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, DateTime
from sqlmodel import SQLModel, Field
from sqlalchemy.dialects.postgresql import JSONB
from app.utils.time import utc_now_datetime

class CheckIn(SQLModel, table=True):
    __tablename__ = "checkins"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    # FK para cliente
    client_id: str = Field(foreign_key="clients.id", index=True)

    # Trainer que criou o check-in
    requested_by_trainer_id: str = Field(foreign_key="users.id", index=True)

    # Status do check-in (pendente ou completado ou skipped)
    status: str = Field(default="pending", max_length=20, index=True) # pending, completed, skipped

    # Dados biométricos recolhidos no check-in
    weight_kg: Optional[float] = Field(default=None, ge=20.0, le=400.0)
    body_fat: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    # Estrutura esperada do dict:
    #   appetite: str           — normal | aumentado | diminuído
    #   intestinal_transit: str — texto livre
    #   plan_adherence_pct: int — 0 a 100
    #   training_performance: int — 1 a 5
    #   recovery_quality: int   — 1 a 5
    #   energy_level: int       — 1 a 5
    #   body_response: str      — texto livre
    #   weeks_on_plan: int      — nº semanas com o plano atual
    #   daily_water_intake_l: float
    #   stress_level: int       — 1 a 5
    #   injuries: str           — lesões ou dores novas
    questionnaire: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB, nullable=True))

    #Notas do cliente ou do trainer
    client_notes: Optional[str] = Field(default=None, max_length=500)
    trainer_notes: Optional[str] = Field(default=None, max_length=500)

    #Fotos do progresso (URLs ou caminhos para as imagens)
    photos: Optional[Dict[str, str]] = Field(default=None, sa_column=Column(JSONB, nullable=True)) #ex: {"front": "url1", "side": "url2", "back": "url3"}

    requested_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))
    completed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))