from fastapi import FastAPI

#importa a função de inicialização do banco de dados(criação de tabelas)
from app.db.init_db import init_db  

app = FastAPI(
    title="PT Manager API",
    version= "0.1.0",
)

@app.on_event("startup")
def on_startup() -> None:
    """
    Hook de statup do FastAPI.
    -Garante que a BD/tabelas existam
    -Em produção, trocariamos isto por migração (Alembic)
    """
    init_db()

@app.get("/health", tags=["health"])
def health_check() -> dict:
    """
    Endpoint simples para verificar se a app está de pé
    """
    return {"status": "ok"}