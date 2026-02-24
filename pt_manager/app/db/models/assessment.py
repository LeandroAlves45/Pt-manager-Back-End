"""
Modelos ORM para o sistema de Avaliações fisicas

Estrutura das tabelas:
    assesments -registo principal de cada avaliação
    measurements - perimetros e composições corporais, ligados a uma avaliação
    assesment_photos - fotos de progresso, ligadas a uma avaliação

O questionário é guardado como JSONB dentro de 'assesments'
para evitar uma tabela extra com colunas estáticas e permitir
adicionar campos futuramente.
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import SQLModel, Field
from sqlalchemy.dialects.postgresql import JSONB

from app.utils.time import utc_now_datetime

class Assessment(SQLModel, table=True):
    """
    Registo principal de uma avaliação física.

    Notas:
    - 'questionnaire' é JSONB: permite adicionar perguntas futuras
      sem alterar o schema da tabela.
    - 'archived_at' implementa soft-delete, preservando histórico.
    - 'created_at' usa datetime (não date) para ordenação cronológica
      precisa quando existem múltiplas avaliações no mesmo dia.
    """

    __tablename__ = "assessments"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    
    #Fk para cliente
    client_id: str = Field(foreign_key="clients.id", index=True)

    #Dados biométricos
    weight_kg: float = Field(ge=0.0, le=500.0)
    body_fat: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    notes: Optional[str] = Field(default=None, max_length=500)

    #Questionário armazenado como JSONB
    questionnaire: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB, nullable=True))

    #Soft delete
    archived_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    #Timestamps
    created_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=utc_now_datetime))

class AssessmentMeasurement(SQLModel, table=True):
    """
    Perímetros e composições corporais ligados a uma avaliação física.
    """

    __tablename__ = "assessment_measurements"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    #Fk para avaliação
    assessment_id: str = Field(foreign_key="assessments.id", index=True)

    #tipo de medição: 'waist', 'hip', 'biceps', 'thigh', 'calf', etc
    measurement_type: str = Field(max_length=50, index=True)

    #Valor em cm
    value_cm: float = Field(ge=0.0, le=300.0)

    created_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))

    #Evita duplicado: um tipo de medição por avaliação
    __table_args__ = (UniqueConstraint('assessment_id', 'measurement_type', name='uix_assessment_measurement_type'),)

class AssessmentPhoto(SQLModel, table=True):
    """
    Fotos de progresso ligadas a uma avaliação física.
    Apenas a Url da foto é armazenada, as imagens ficam em serviço externo.

    photo_type indica a posição da foto: 'front', 'side', 'back'
    """

    __tablename__ = "assessment_photos"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    #Fk para avaliação
    assessment_id: str = Field(foreign_key="assessments.id", index=True)

    #tipo de foto: 'front', 'side', 'back'
    photo_type: str = Field(min_length=1, max_length=50, index=True)

    #URL da foto armazenada 
    url: str = Field(min_length=1, max_length=500)

    created_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))