import uuid
from datetime import date
from typing import Optional

from pydantic import validator
from sqlmodel import Field, SQLModel, UniqueConstraint
from app.utils.time import utc_now


#catalogo de exercicios
class Exercise(SQLModel, table=True):
    """
    Tabela que armazena todos os exercícios disponíveis no sistema.
    Serve como catálogo para ser referenciado nos planos de treino.
    """

    __tablename__ = "exercises"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    name: str = Field(index=True, min_length=1)
    muscles: str = Field(index=True, min_length=1) #ex: "biceps, triceps"
    url: Optional[str] = Field(default=None, max_length=500)
    is_active: bool = Field(default=True, index=True)

    #Multi-tenancy:
    # Null = global (visível para todos os trainers)
    # FK = privado (visível apenas para o trainer que criou o exercício)
    owner_trainer_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)

    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)

#cabeçalho do plano de treino
class TrainingPlan(SQLModel, table=True):
    """
    Plano de treino completo. Pode ser:
    - Template (client_id = None): modelo reutilizável
    - Plano de cliente (client_id preenchido): atribuído a cliente específico
    """
    __tablename__ = "training_plans"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    client_id: Optional[str] = Field(default=None, foreign_key="clients.id", index=True)

    #Trainer dono deste plano (obrigatório)
    #Preenchido automaticamente no endpoint com o ID do trainer autenticado
    owner_trainer_id: str = Field(foreign_key="users.id", index=True)
    
    name: str = Field(index=True, min_length=1) # Nome do plano (ex: "Hipertrofia Iniciante", "Template Força")
    status: str = Field(default="draft", index=True, max_length=20) #draft, published, archived
    start_date: Optional[date] = Field(default=None, index=True)
    end_date: Optional[date] = Field(default=None, index=True)
    notes: Optional[str] = Field(default=None)

    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)
    archived_at: Optional[date] = Field(default=None, index=True)

    @validator('end_date')
    def end_date_after_start(cls, v, values):
        """
        Valida que a data de fim é posterior à data de início
        """
        if v and 'start_date' in values and values['start_date']:
            if v < values['start_date']:
                raise ValueError('end_date deve ser posterior a start_date')
        return v

#class para os dias do plano de treino
class TrainingPlanDay(SQLModel, table=True):
    """
    Representa um dia específico dentro do plano de treino.
    Ex: "Dia A - Peito e Tríceps", "Dia B - Costas e Bíceps"
    """

    __tablename__ = "training_plan_days"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    plan_id: str = Field(foreign_key="training_plans.id", index=True)

    name: str = Field(min_length=1)  # Nome do dia (ex: "Peito e Tríceps")
    order_index: int = Field(default= 0, ge= 0, index=True) # Ordem de execução (0, 1, 2... para ordenar os dias)
    notes: Optional[str] = Field(default=None)

    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)

#associação entre dias do plano e exercicios
class PlanDayExercise(SQLModel, table=True):
    """
    Liga um exercício específico a um dia do plano, com todos os parâmetros
    de execução (séries, repetições, descanso, etc.)
    """

    __tablename__ = "plan_day_exercises"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    plan_day_id: str = Field(foreign_key="training_plan_days.id", index=True)

    exercise_id: str = Field(foreign_key="exercises.id", index=True)
    order_index: int = Field(default=0, ge=0, index=True) #adicionar order_index para ordenar exercícios no dia
    sets: int = Field(ge=1, le=15)
    reps_range: str = Field(min_length=1, max_length=50) #ex: "8-12"
    rest_range_seconds: Optional[str] = Field(default= None, max_length=50) #ex: "30-60"
    tempo: Optional[str] = Field(default=None, max_length=50) #ex: "2-1-2"
    is_superset_group: Optional[str] = Field(default=None, max_length=20) #ex: "A", "B" para indicar que exercícios fazem parte do mesmo superset
    substitution_allowed: Optional[bool] = Field(default=False)
    notes: Optional[str] = Field(default=None)

    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)

#class para registar a carga por série
class PlanExerciseSetLoad(SQLModel, table=True):
    """
    Armazena a carga planejada para cada série individual de um exercício.
    Permite progressão detalhada (ex: série 1 = 80kg, série 2 = 85kg, série 3 = 90kg)
    """

    __tablename__ = "plan_exercise_set_loads"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    plan_day_exercise_id: str = Field(foreign_key="plan_day_exercises.id", index=True)
    set_number: int = Field(ge=1, le=15)
    load_kg: Optional[float] = Field(default=None, ge=0.0)
    notes: Optional[str] = Field(default=None)
    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)

    # Adicionar constraint única para evitar duplicados
    __table_args__ = (
        # Garante que não existem 2 registos com mesmo exercício + número de série
        UniqueConstraint('plan_day_exercise_id', 'set_number', name='uix_exercise_set'),
    )

#mapeia o plano ativo do cliente
class ClientActivePlan(SQLModel, table=True):
    """
    Histórico de planos ativos do cliente.
    Permite rastrear qual plano está ativo e mudanças ao longo do tempo.
    - active_to = None: plano atualmente ativo
    - active_to preenchido: plano que já foi encerrado
    """

    __tablename__ = "client_active_plans"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    client_id: str = Field(foreign_key="clients.id", index=True)
    training_plan_id: str = Field(foreign_key="training_plans.id", index=True)
    active_from: date = Field(default_factory=utc_now, index=True)
    active_to: Optional[date] = Field(default=None, index=True)

    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)