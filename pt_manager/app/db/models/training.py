import uuid
from datetime import date
from typing import Optional

from sqlmodel import Field, SQLModel
from app.utils.time import utc_now


#catalogo de exercicios
class Exercise(SQLModel, table=True):

    __tablename__ = "exercises"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    name: str = Field(index=True, min_length=1)
    muscles: str = Field(index=True, min_length=1) #ex: "biceps, triceps"
    url: Optional[str] = Field(default=None, max_length=500)
    is_active: bool = Field(default=True, index=True)
    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)

#cabeçalho do plano de treino
class TrainingPlan(SQLModel, table=True):

    __tablename__ = "training_plans"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    name: str = Field(index=True, min_length=1)
    status: str = Field(default="draft", index=True, max_length=20) #draft, published, archived
    start_date: Optional[date] = Field(default=None, index=True)
    end_date: Optional[date] = Field(default=None, index=True)
    notes: Optional[str] = Field(default=None)
    #exercises: str = Field(index=True, min_length=1) #ex: "exercise_id1, exercise_id2"
    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)

#class para os dias do plano de treino
class TrainingPlanDay(SQLModel, table=True):

    __tablename__ = "training_plan_days"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    plan_id: str = Field(foreign_key="training_plans.id", index=True)
    name: str = Field(min_length=1)
    order_index: int = Field(default= 0, ge= 0, index=True)
    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)

#associação entre dias do plano e exercicios
class PlanDayExercise(SQLModel, table=True):

    __tablename__ = "plan_day_exercises"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    plan_day_id: str = Field(foreign_key="training_plan_days.id", index=True)
    exercise_id: str = Field(foreign_key="exercises.id", index=True)
    sets: int = Field(ge=1, le=15)
    reps_range: str = Field(min_length=1, max_length=50) #ex: "8-12"
    rest_range_seconds: Optional[str] = Field(default= None, max_length=50) #ex: "30-60"
    tempo: Optional[str] = Field(default=None, max_length=50) #ex: "2-1-2"
    is_superset: Optional[str] = Field(default=None, max_length=20) #yes, no
    substitution_allowed: Optional[bool] = Field(default=False)
    notes: Optional[str] = Field(default=None)
    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)

#class para registar a carga por série
class PlanExerciseSetLoad(SQLModel, table=True):

    __tablename__ = "plan_exercise_set_loads"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    plan_day_exercise_id: str = Field(foreign_key="plan_day_exercises.id", index=True)
    set_number: int = Field(ge=1, le=15)
    load_kg: Optional[float] = Field(default=None, ge=0.0)
    notes: Optional[str] = Field(default=None)
    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)

#mapeia o plano ativo do cliente
class ClientActivePlan(SQLModel, table=True):

    __tablename__ = "client_active_plans"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    client_id: str = Field(foreign_key="clients.id", index=True)
    training_plan_id: str = Field(foreign_key="training_plans.id", index=True)
    active_from: date = Field(default_factory=utc_now, index=True)
    active_to: Optional[date] = Field(default=None, index=True)
    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)