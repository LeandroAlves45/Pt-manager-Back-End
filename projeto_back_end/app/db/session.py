from sqlmodel import Session, create_engine
from app.core.config import settings


def _get_connect_args() -> dict:
    #retorna argumentos de conexão específicos para cada tipo de banco de dados
    if settings.database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


#Postgre SQL com Dbeaver para visualizar
engine = create_engine(settings.database_url, echo=False, connect_args=_get_connect_args(), pool_pre_ping=True)

def get_session():
    """
    Dependency FastAPI that will return a database session
    Garante uma sessão por request
    """
    with Session(engine) as session:
        yield session