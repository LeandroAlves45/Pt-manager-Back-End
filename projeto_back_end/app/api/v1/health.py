from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from app.api.deps import db_session

router = APIRouter(prefix="/health", tags=["health"])

@router.get("")
async def health_check(session: Session = Depends(db_session)):
    """
    Endpoint de health check para monitoramento.
    
    Verifica:
    - API está respondendo
    - Conexão com banco de dados funciona
    
    Returns:
        {"status": "healthy", "database": "connected"}
    """
    try:
        # Testar conexão com DB
        session.exec(select(1)).first()
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }