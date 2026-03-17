"""
Ponto de entrada da aplicação FastAPI — app factory e configuração global.
 
Responsabilidades deste ficheiro:
    - Criar a instância FastAPI com metadados
    - Configurar CORS (origens permitidas vindas do .env)
    - Registar todos os routers com os seus prefixos e dependências
    - Hooks de startup: init_db, migrations, scheduler, seed data
    - Hook de shutdown: desligar o scheduler graciosamente
 
Convenção de routers:
    Routers públicos (sem JWT): auth, signup, stripe_webhook, health
    Routers protegidos por JWT: todos os restantes
    A granularidade fina de permissões (role, subscrição) é gerida
    dentro de cada router individualmente via Depends.
"""

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import logging

logger = logging.getLogger(__name__)

from app.core.security import require_api_key, get_current_user
from app.core.logging import setup_logging
from app.core.config import settings

from app.db.init_db import init_db  
from app.db.session import engine
from app.db.seeds.pack_types import seed_pack_types
from app.db.seeds.superuser import seed_superuser
from app.db.seeds.demo_data import seed_demo_data

from sqlmodel import Session

# ----------------------------------------------
# Routers da API
# ----------------------------------------------
from app.api.v1.clients import router as clients_router
from app.api.v1.checkins import router as checkins_router
from app.api.v1.packs import router as packs_router
from app.api.v1.pack_types import router as pack_types_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.training_plans import router as training_plans_router
from app.api.v1.exercises import router as exercises_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.health import router as health_router
from app.api.v1.assessments import router as assessments_router
from app.api.v1.nutrition import router as nutrition_router
from app.api.v1.supplements import router as supplements_router
from app.api.v1.auth import router as auth_router
from app.api.v1.signup import router as signup_router
from app.api.v1.stripe_webhook import router as webhooks_router
from app.api.v1.billing import router as billing_router
from app.api.v1.admin import router as admin_router
from app.api.v1.trainer_profile import router as trainer_profile_router
from app.api.v1.client_portal import router as client_portal_router
from app.api.v1.client_supplements import router as client_supplements_router

from app.scheduler import start_scheduler, shutdown_scheduler


# Garante que a pasta de logs existe antes de configurar o logging
os.makedirs("logs", exist_ok=True) 
setup_logging()

# ----------------------------------------------
# Criação da instância FastAPI
# ----------------------------------------------

app = FastAPI(
    title="PT Manager API",
    version= "0.1.0",
    description="API multi-tenant para gestão de clientes de Personal Trainers.",
)

# -------------------------------------------------------
# Handler global de excepções
#
# Sem este handler, erros inesperados devolvem stack traces completos
# ao cliente — expõe detalhes da implementação em produção.
#
# Comportamento:
#   - HTTPException: deixa passar normalmente (tem status_code próprio)
#   - Qualquer outra Exception: devolve 500 genérico e regista o erro no log
# -------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Captura qualquer excepção não tratada e devolve uma resposta 500 genérica.
    O stack trace real é registado no log para diagnóstico, mas nunca exposto ao cliente.
    """
    if isinstance(exc, HTTPException):
        # Deixa passar HTTPExceptions para que o FastAPI as trate normalmente
        raise exc
    
    # Para outras exceções, regista o erro e devolve uma resposta genérica
    logger.error(
        f"Erro não tratado em {request.method} {request.url}: {exc}",
        exc_info=True,
    )
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Ocorreu um erro inesperado. Por favor, tente novamente."}
    )

# ----------------------------------------------
# Configuração de CORS
# ----------------------------------------------

origins = [origin.strip() for origin in settings.cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------
# Hooks de ciclo de vida da aplicação
# ----------------------------------------------
    
@app.on_event("startup")
def on_startup() -> None:
    """
    Executado uma vez quando o servidor arranca.
 
    Ordem de execução no startup (não alterar):
        1. init_db        — cria tabelas via SQLModel metadata
        2. run_migrations — executa SQL idempotente (001 → 004...)
        3. seed_pack_types — pack types por defeito
        4. seed_superuser  — conta de superuser permanente
        5. start_scheduler — job de notificações em background
    """

    # Cria tabelas que ainda não existam 
    init_db()  
    
    from app.db.migrate import run_migrations
    run_migrations()

    with Session(engine) as session:
        seed_pack_types(session)
        seed_superuser(session)
        seed_demo_data(session)

    start_scheduler()


    
        

@app.on_event("shutdown")
def on_shutdown() -> None:
    """
    Executado quando o servidor é encerrado (SIGTERM em Railway).
    Desliga o scheduler graciosamente para evitar jobs a meio.
    """
    shutdown_scheduler()

# --------------------------------------
# Dependência global de API Key — aplicada a TODAS os routers abaixo
# --------------------------------------

common_dependencies = [Depends(require_api_key)]

# --------------------------------------
# Router Públicos (requerem apenas API Key, sem JWT)
# --------------------------------------

# auth e signup: login e registo não precisam de estar autenticados
app.include_router(auth_router, prefix="/api/v1")
app.include_router(signup_router, prefix="/api/v1")

# Stripe webhooks: autenticados via HMAC signature, não via JWT
app.include_router(webhooks_router, prefix="/api/v1")

# Health check: público para monitorização externa (ex: Railway, UptimeRobot)
app.include_router(health_router, prefix="/api/v1")

# ---------------------------------------------------------------------------
# Rotas PROTEGIDAS por JWT
#
# A permissão fina (role, subscrição activa) é verificada dentro de
# cada router via Depends(require_trainer), Depends(require_active_subscription), etc.
# ---------------------------------------------------------------------------

jwt_dependency = [Depends(get_current_user)]

app.include_router(clients_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(supplements_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(billing_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(admin_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(packs_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(pack_types_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(sessions_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(trainer_profile_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(training_plans_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(exercises_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(notifications_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(assessments_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(nutrition_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(checkins_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(client_portal_router, prefix="/api/v1", dependencies=jwt_dependency)
app.include_router(client_supplements_router, prefix="/api/v1", dependencies=jwt_dependency)
