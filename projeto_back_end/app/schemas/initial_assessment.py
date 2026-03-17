from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class HealthQuestionnaire(BaseModel):
    """
    Estrutura do questionário de saúde inicial.
    Todos os campos são opcionais — o trainer preenche o que conseguir
    recolher na primeira sessão.
    """
    # SECÇÃO 1 — IDENTIFICAÇÃO
    occupation: Optional[str] = Field(default=None, max_length=100) #profissão (ex: "professor", "escritório")
    activity_level: Optional[str] = Field(default=None, max_length=50) #sedentário | levemente ativo | moderadamente ativo | muito ativo

    # SECÇÃO 2 — HISTORIAL DE SAÚDE
    medical_conditions: Optional[str] = Field(default=None, max_length=500) #doenças diagnosticadas (diabetes, hipertensão, etc.)
    medications: Optional[str] = Field(default=None, max_length=500) #medicação atual
    injuries: Optional[str] = Field(default=None, max_length=500) #lesões passadas ou atuais
    surgeries: Optional[str] = Field(default=None, max_length=500) #cirurgias relevantes
    family_history: Optional[str] = Field(default=None, max_length=500) #historial familiar relevante

    # SECÇÃO 3 — HÁBITOS DE VIDA
    sleep_hours: Optional[float] = Field(default=None, ge=0.0, le=24.0) #horas de sono por noite
    sleep_quality: Optional[str] = Field(default=None, max_length=20) #boa | razoável | má
    stress_level: Optional[int] = Field(default=None, ge=1, le=5) #1 a 5
    smoking: Optional[bool] = Field(default=None) #fumador
    alcohol: Optional[str] = Field(default=None, max_length=50) #nunca | ocasional | frequente
    water_intake_l: Optional[float] = Field(default=None, ge=0.0, le=10.0) #litros de água por dia

    # SECÇÃO 4 — HISTORIAL DESPORTIVO
    previus_trainig: Optional[str] = None
    sports_practiced: Optional[str] = None
    training_frequency: Optional[int] = Field(default=None, ge=0, le=7) #dias de treino por semana (atual)

    # SECÇÃO 5 — OBJETIVOS
    goals: Optional[str] = Field(default=None, max_length=500) #objetivos do cliente (perda de peso, ganho muscular, etc.)

    # SECÇÃO 6 — ALIMENTAÇÃO
    dietary_restrictions: Optional[str] = None #restrições alimentares (ex: "vegetariano", "sem glúten")
    meal_frequency: Optional[int] = Field(default=None, ge=0, le=10) #número de refeições por dia
    supplements_current: Optional[str] = None #suplementação atual (ex: "whey protein, creatina")

    # SECÇÃO 7 — PREFERÊNCIAS DE TREINO
    preferred_schedule: Optional[str] = None #preferência de horário para treino (ex: "manhã", "tarde", "noite")
    gym_access: Optional[bool] = None #tem acesso a ginásio
    equipment_available: Optional[str] = None #equipamento disponível para treino (ex: "halteres, elásticos")
    limitations: Optional[str] = None #limitações físicas para o treino (ex: "joelho direito", "hipertensão")

class InitialAssessmentCreate(BaseModel):
    """
    Payload para criação de uma avaliação física inicial.
    Inclui dados biométricos e o questionário de saúde.
    """
    client_id: str 
    weight_kg: Optional[float] = Field(default=None, ge=20.0, le=400.0)
    height_cm: Optional[float] = Field(default=None, ge=80, le=260)
    body_fat: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    health_questionnaire: Optional[HealthQuestionnaire] = None
    notes: Optional[str] = Field(default=None, max_length=1000)

class InitialAssessmentRead(BaseModel):
    """
    Schema para leitura de dados da avaliação física inicial.
    usado em respostas de API
    """
    id: str
    client_id: str
    assessed_by_trainer_id: str
    weight_kg: Optional[float]
    height_cm: Optional[float]
    body_fat: Optional[float]
    health_questionnaire: Optional[HealthQuestionnaire]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class InitialAssessmentUpdate(BaseModel):
    """
    Payload para atualização de uma avaliação física inicial.
    todos os campos são opcionais
    """
    weight_kg: Optional[float] = Field(default=None, ge=20.0, le=400.0)
    height_cm: Optional[float] = Field(default=None, ge=80, le=260)
    body_fat: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    health_questionnaire: Optional[HealthQuestionnaire] = None
    notes: Optional[str] = Field(default=None, max_length=1000)