from fastapi import FastAPI
from app.core.security import require_api_key
from fastapi import Depends
from sqlmodel import Session

#importa a função de inicialização do banco de dados(criação de tabelas)
from app.db.init_db import init_db  
from app.db.session import engine
from app.db.seeds.pack_types import seed_pack_types
from app.api.v1.clients import router as clients_router
from app.api.v1.packs import router as packs_router
from app.api.v1.pack_types import router as pack_types_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.training_plans import router as training_plans_router
from app.api.v1.exercises import router as exercises_router
from app.scheduler import start_scheduler, shutdown_scheduler

app = FastAPI(
    title="PT Manager API",
    version= "0.1.0",
)


@app.on_event("startup")
def on_startup() -> None:
    """
    Hook de startup do FastAPI.
    
    Nota: Em produção, execute migrations com Alembic antes de iniciar a app:
    $ alembic upgrade head
    $ uvicorn app.main:app
    """
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