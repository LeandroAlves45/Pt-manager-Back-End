from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.core.security import require_api_key
from app.api.deps import db_session
from sqlmodel import Session

#importa a função de inicialização do banco de dados(criação de tabelas)
from app.db.init_db import init_db  
from app.db.session import engine
from app.db.seeds.pack_types import seed_pack_types

#Routers da API
from app.api.v1.clients import router as clients_router
from app.api.v1.packs import router as packs_router
from app.api.v1.pack_types import router as pack_types_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.training_plans import router as training_plans_router
from app.api.v1.exercises import router as exercises_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.health import router as health_router
from app.api.v1.assessments import router as assessments_router
from app.api.v1.nutrition import router as nutrition_router

from app.scheduler import start_scheduler, shutdown_scheduler
from app.core.logging import setup_logging
from app.core.config import settings
import os


os.makedirs("logs", exist_ok=True)  # garante que a pasta de logs exista
setup_logging()

app = FastAPI(
    title="PT Manager API",
    version= "0.1.0",
)

# Configuração de CORS
origins = [origin.strip() for origin in settings.cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sem autenticação para health check
app.include_router(health_router, prefix="/api/v1")
    
@app.on_event("startup")
def on_startup() -> None:
    """
    Hook de startup do FastAPI.
    
    Nota: Em produção, execute migrations com Alembic antes de iniciar a app:
    $ alembic upgrade head
    $ uvicorn app.main:app
    """
    init_db()  # Garante que as tabelas existam (útil para desenvolvimento)
    
    start_scheduler()
    with Session(engine) as session:
        seed_pack_types(session)

@app.on_event("shutdown")
def on_shutdown() -> None:
    # Hook de shutdown do FastAPI para desligar o scheduler quando a aplicação for encerrada.
    shutdown_scheduler()

#Protege todas as rotas 
common_dependencies = [Depends(require_api_key)]
#versão da API (V1)
app.include_router(clients_router, prefix="/api/v1", dependencies=common_dependencies)
app.include_router(packs_router, prefix="/api/v1", dependencies=common_dependencies)
app.include_router(pack_types_router, prefix="/api/v1", dependencies=common_dependencies)
app.include_router(sessions_router, prefix="/api/v1", dependencies=common_dependencies)
app.include_router(training_plans_router, prefix="/api/v1", dependencies=common_dependencies)
app.include_router(exercises_router, prefix="/api/v1", dependencies=common_dependencies)
app.include_router(notifications_router, prefix="/api/v1", dependencies=common_dependencies)
app.include_router(assessments_router, prefix="/api/v1", dependencies=common_dependencies)
app.include_router(nutrition_router, prefix="/api/v1", dependencies=common_dependencies)