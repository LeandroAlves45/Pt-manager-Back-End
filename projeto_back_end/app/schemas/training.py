from typing import List, Optional
from datetime import date
from sqlmodel import SQLModel, Field

#======================
#Exercises
#======================

class ExerciseCreate(SQLModel):
    #payload para criar exercicio
    name: str = Field(min_length=1)
    muscles: str = Field(min_length=1)  # ex: "biceps, triceps"
    url: Optional[str] = Field(default=None, max_length=500)
    is_active: bool = True

class ExerciseUpdate(SQLModel):
    #payload para atualizar exercicio
    name: Optional[str] = Field(default=None, min_length=1)
    muscles: Optional[str] = Field(default=None, min_length=1)  # ex: "biceps, triceps"
    url: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None

class ExerciseRead(SQLModel):
    #modelo para leitura de exercicio
    id: str
    name: str
    muscles: str
    url: Optional[str] = None
    is_active: bool
    created_at: date
    updated_at: date

#======================
#Training Plans
#======================

class TrainingPlanCreate(SQLModel):
    #payload para criar plano de treino
    client_id: Optional[str] = None
    name: str = Field(min_length=1) #nome do plano é obrigatório
    status: Optional[str] = Field(default="draft", max_length=20)  # draft, published, archived
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None

class TrainingPlanUpdate(SQLModel):
    #payload para atualizar plano de treino
    client_id: Optional[str] = None
    name: Optional[str] = Field(default=None, min_length=1)
    status: Optional[str] = Field(default=None, max_length=20)  # draft, published, archived
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None

class TrainingPlanRead(SQLModel):
    #modelo para leitura de plano de treino
    id: str
    client_id: Optional[str] = None
    name: str
    status: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None
    created_at: date
    updated_at: date

#======================
#Training Plan Days
#======================

class TrainingPlanDayCreate(SQLModel):
    #payload para criar dia do plano de treino
    name: str = Field(min_length=1)
    order_index: int = Field(default=0, ge=0)
    notes: Optional[str] = None

class TrainingPlanDayUpdate(SQLModel):
    #payload para atualizar dia do plano de treino
    name: Optional[str] = Field(default=None, min_length=1)
    order_index: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None

class TrainingPlanDayRead(SQLModel):
    #modelo para leitura de dia do plano de treino
    id: str
    plan_id: str
    name: str
    order_index: int
    notes: Optional[str] = None
    created_at: date
    updated_at: date

#======================
#Plan Day Exercises
#======================

class PlanDayExerciseCreate(SQLModel):
    """
    Payload para criar associação entre dia do plano e exercício
    """
    plan_day_id: str
    exercise_id: str
    order_index: int = Field(default=0, ge=0)
    sets: int = Field(ge=1, le=15)
    reps_range: str = Field(min_length=1, max_length=50)  # ex: "8-12"
    rest_range_seconds: Optional[str] = Field(default=None, max_length=50)  # ex: "30-60"
    tempo: Optional[str] = Field(default=None, max_length=50)  # ex: "2-1-2"
    is_superset_group: Optional[str] = Field(default=None, max_length=20)  # yes, no
    substitution_allowed: Optional[bool] = False
    notes: Optional[str] = None

class PlanDayExerciseUpdate(SQLModel):
    """
    Payload para atualizar associação entre dia do plano e exercício
    """
    exercise_id: Optional[str] = None
    order_index: Optional[int] = None
    sets: Optional[int] = Field(default=None, ge=1, le=15)
    reps_range: Optional[str] = Field(default=None, min_length=1, max_length=50)  # ex: "8-12"
    rest_range_seconds: Optional[str] = Field(default=None, max_length=50)  # ex: "30-60"
    tempo: Optional[str] = Field(default=None, max_length=50)  # ex: "2-1-2"
    is_superset_group: Optional[str] = Field(default=None, max_length=20)  # yes, no
    substitution_allowed: Optional[bool] = None
    notes: Optional[str] = None

class PlanDayExerciseRead(SQLModel):
    """
    Modelo para leitura de associação entre dia do plano e exercício
    """
    id: str
    plan_day_id: str
    exercise_id: str
    exercise_name:str
    exercise_muscles:str
    exercise_url: Optional[str] = None
    order_index: int
    sets: int
    reps_range: str
    rest_range_seconds: Optional[str] = None
    tempo: Optional[str] = None
    is_superset_group: Optional[str] = None
    substitution_allowed: Optional[bool] = None
    notes: Optional[str] = None
    created_at: date
    updated_at: date

#======================
#set Load
#======================
    
class PlanExerciseSetLoadCreate(SQLModel):
    """
    Payload para criar registo de carga por série.
    O plan_day_exercise_id vem do path parameter, não do body.
    """
    set_number: int = Field(ge=1, le=15)
    load_kg: Optional[float] = Field(default=None, ge=0.0)
    notes: Optional[str] = None

class PlanExerciseSetLoadUpdate(SQLModel):
    #payload para atualizar registo de carga por série
    set_number: Optional[int] = Field(default=None, ge=1, le=15)
    load_kg: Optional[float] = Field(default=None, ge=0.0)
    notes: Optional[str] = None

class PlanExerciseSetLoadRead(SQLModel):
    #modelo para leitura de registo de carga por série
    id: str
    plan_day_exercise_id: str
    exercise_id: str
    exercise_name: str
    exercise_muscles: str
    set_number: int
    load_kg: Optional[float] = None
    notes: Optional[str] = None
    created_at: date
    updated_at: date

#======================
#Client Active Plan
#======================

class ClientActivePlanCreate(SQLModel):
    #payload para mapear plano ativo do cliente
    client_id: str
    training_plan_id: str
    active_from: Optional[date] = None

class ClientActivePlanRead(SQLModel):
    #modelo para leitura de plano ativo do cliente
    id: str
    client_id: str
    training_plan_id: str
    active_from: date
    active_to: Optional[date] = None
    created_at: date
    updated_at: date

#Class clone para clone de plano de treino
class ClonePlanToClientCreate(SQLModel):
    #payload para clonar plano de treino
    client_id: str = Field(min_length=1)
    name: Optional[str] = Field(default=None, min_length=1)
    activate: bool = False
    activate_from: Optional[date] = None

class ClientActivePlanRead(SQLModel):
    """
    Modelo para leitura de plano ativo do cliente.
    Inclui informações do cliente e do plano para facilitar visualização.
    """
    # Campos do ClientActivePlan
    id: str
    client_id: str
    client_full_name: str
    training_plan_id: str
    training_plan_name: str
    active_from: date
    active_to: Optional[date] = None
    created_at: date
    updated_at: date
    

    