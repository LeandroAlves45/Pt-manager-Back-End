"""
Modelos ORM para o sistem de Nutrição

Estrutura:
foods - tabela principal de alimentos, com macros por 100g
meal_plans - plano alimentar diário, ligado a um cliente, com itens de refeição
meal_plans_meal -refeições dentro do plano (pequeno-almoço, almoço, jantar, lanches)
meal_plan_items - itens de refeição, ligados a um plano e a um alimento, com quantidade em gramas

MealPlan recebe 'plan_type' e campos de target de macros (definidos pelo PT).
Um cliente pode ter múltiplos planos ativos em simultâneo — um por tipo de dia.
"""

import uuid
from datetime import datetime,date
from typing import Optional

from sqlalchemy import Column, DateTime, String, Computed, Numeric
from sqlmodel import SQLModel, Field

from app.utils.time import utc_now_datetime

#Valores válidos para plan_type - guardado como VARCHAR no banco de dados
PLAN_TYPE_OPTIONS = {
    "training_day": "Dia de treino",
    "rest_day": "Dia de descanso",
    "upper_body_day": "Dia de treino de parte superior",
    "lower_body_day": "Dia de treino de parte inferior",
    "refeed_day": "Dia de refeed",
    "competition_day": "Dia de competição",
    "custom": "Personalizado",
}

class Food(SQLModel, table=True):
    """
    Catálogo de alimentos com macros por 100g.

    Formula de kcal: (carbs*4 + protein*4 + fats*9) é implementada como coluna GENERATED no PostgreSQL,
    """

    __tablename__ = "foods"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    name: str = Field(min_length=1, max_length=100, index=True)

    #Macros por 100g
    carbs: float = Field(ge=0, le=100.0)
    protein: float = Field(ge=0, le=100.0)
    fats: float = Field(ge=0, le=100.0)

    #Coluna gerada no PostgreSQL para garantir consistência do valor de kcal
    kcal: Optional[float] = Field(default=None, sa_column=Column(Numeric(precision=6, scale=2), Computed("(carbs*4) + (protein*4) + (fats*9)", persisted=True), nullable=True))

    is_active: bool = Field(default=True)

    #Multi-tenancy:
    # Null = global (visível para todos os trainers)
    # value= privado do trainer (visível apenas para o trainer que criou o alimento)
    owner_trainer_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)

    created_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))

class MealPlan(SQLModel, table=True):
    """
    Cabeçalho do plano alimentar diário, ligado a um cliente.

    Um cliente pode ter multiplos planos ao longo do tempo, mas apenas um plano ativo por dia.
    """

    __tablename__ = "meal_plans"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    
    #Fk para cliente
    client_id: str = Field(foreign_key="clients.id", index=True)

    #Trainer dono deste plano 
    owner_trainer_id: str = Field(foreign_key="users.id", index=True)

    name:str = Field(min_length=1, max_length=100) #nome do plano, ex: "Plano de 2024-06-01"

    #tipo de plano alimentar, ex: "training_day", "rest_day", "refeed_day". Define os campos de target de macros que o PT deve preencher no plano.
    plan_type: str = Field(default=None, sa_column=Column(String(50), nullable=True, index=True))

    starts_date: Optional[date] = Field(index=True)
    ends_date: Optional[date] = Field(index=True)

    # Múltiplos planos podem estar ativos (um por plan_type)
    # A unicidade (client + plan_type ativo) é aplicada na camada de aplicação
    active: bool = Field(default=True, index=True)

    notes: Optional[str] = Field(default=None, max_length=1000)

    # --- Targets de macros definidos pelo PT ---
    # Opcionais: podem ser preenchidos na criação ou atualizados depois via PATCH.
    # Não são calculados automaticamente — o PT escolhe após ver /calculate-macros.

    kcal_target: Optional[float] = Field(default=None, ge=0) #target de calorias para o plano
    carbs_target: Optional[float] = Field(default=None, ge=0) #target de carboidratos em gramas para o plano
    protein_target: Optional[float] = Field(default=None, ge=0) #target de proteínas em gramas para o plano
    fats_target: Optional[float] = Field(default=None, ge=0) #target de gorduras em gramas para o plano

    archived_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))

class MealPlanMeal(SQLModel, table=True):
    """
    Refeições dentro do plano alimentar (ex: pequeno-almoço, almoço, jantar, lanches).
    """

    __tablename__ = "meal_plans_meal"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    #Fk para plano alimentar
    meal_plan_id: str = Field(foreign_key="meal_plans.id", index=True)

    name: str = Field(min_length=1, max_length=100) #nome da refeição, ex: "Almoço"

    #ordem de exibição das refeições dentro do plano
    order_index: int = Field(default=0,ge=0, index=True)

    created_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))

class MealPlanItem(SQLModel, table=True):
    """
    Linha de um alimento dentro de uma refeição do plano alimentar.
    """

    __tablename__ = "meal_plan_items"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    #Fk para refeição do plano
    meal_id: str = Field(foreign_key="meal_plans_meal.id", index=True)

    #Fk para alimento
    food_id: str = Field(foreign_key="foods.id", index=True)

    quantity_grams: float = Field(ge=0.1, le=7000.0) #quantidade em gramas do alimento para esta linha do plano

    created_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now_datetime, sa_column=Column(DateTime(timezone=True), nullable=False))