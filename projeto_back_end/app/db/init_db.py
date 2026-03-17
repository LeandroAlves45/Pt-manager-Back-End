"""
Inicialização da base de dados.
 
Responsabilidades:
    1. Importar todos os modelos SQLModel para que o metadata fique registado
    2. Criar as tabelas que ainda não existam via SQLModel.metadata.create_all()
    3. Executar as migrações SQL manuais (001, 002, 003, 004, ...)
"""

from sqlmodel import SQLModel
from app.db.session import engine
from app.db.migrate import run_migrations

# Modelos de utilizadores e autenticação
from app.db.models.user import User 
from app.db.models.active_token import ActiveToken 

# Modelos de clientes r subscrições
from app.db.models.client import Client                                      
from app.db.models.trainer_subscription import TrainerSubscription
from app.db.models.trainer_settings import TrainerSettings    

# Modelos de sessões e packs
from app.db.models.session import TrainingSession, PackConsumption          
from app.db.models.pack import PackType, ClientPack   

# Modelos de planos de treino
from app.db.models.training import (                                         
    Exercise,
    TrainingPlan,
    TrainingPlanDay,
    PlanDayExercise,
    PlanExerciseSetLoad,
    ClientActivePlan,
)

# Modelos de avaliações e check ins
from app.db.models.initial_assessment import InitialAssessment               
from app.db.models.checkin import CheckIn 

# Modelos de nutrição e suplementos
from app.db.models.nutrition import Food, MealPlan, MealPlanMeal, MealPlanItem  
from app.db.models.supplement import Supplement
from app.db.models.client_supplement import ClientSupplement 

# Modelos de notificações
from app.db.models.notification import Notification


def init_db() -> None:
    """
    Cria as tabelas na BD caso não existam
    Em produto, isto é substituido por migrações
    """
    SQLModel.metadata.create_all(engine)    
    #executa migrações manuais simples
    run_migrations()