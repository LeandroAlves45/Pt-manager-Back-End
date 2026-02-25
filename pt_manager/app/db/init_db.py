from sqlmodel import SQLModel
from app.db.session import engine
from app.db.migrate import run_migrations

#importar modelos garante que o SQLModel "vê" as tabelas
from app.db.models.client import Client #noqa: F401
from app.db.models.user import User #noqa: F401
from app.db.models.trainer_subscription import TrainerSubscription #noqa: F401
from app.db.models.pack import PackType, ClientPack #noqa: F401
from app.db.models.session import TrainingSession, PackConsumption #noqa: F401
from app.db.models.training import (Exercise, TrainingPlan, TrainingPlanDay, PlanDayExercise, PlanExerciseSetLoad, ClientActivePlan) #noqa: F401
from app.db.models.notification import Notification #noqa: F401
from app.db.models.assessment import Assessment, AssessmentMeasurement, AssessmentPhoto #noqa: F401
from app.db.models.nutrition import Food, MealPlan, MealPlanMeal, MealPlanItem #noqa: F401
from app.db.models.supplement import Supplement #noqa: F401

def init_db() -> None:
    """
    Cria as tabelas na BD caso não existam
    Em produto, isto é substituido por migrações
    """
    SQLModel.metadata.create_all(engine)    
    #executa migrações manuais simples
    run_migrations()