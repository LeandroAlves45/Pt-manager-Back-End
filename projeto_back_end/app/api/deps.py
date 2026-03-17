from typing import Generator
from sqlmodel import Session
from app.db.session import get_session

def db_session() -> Generator[Session, None, None]:
    """
    Dependency that para manter um ponto único de sessão com o banco de dados.
    """
    yield from get_session()