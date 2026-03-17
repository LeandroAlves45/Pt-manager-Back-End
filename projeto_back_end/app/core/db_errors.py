import logging
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session

logger = logging.getLogger(__name__)

def commit_or_rollback (session: Session):
    """
    Tenta fazer commit na sessão; em caso de erro, faz rollback e levanta HTTPException.
    """

    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        logger.error(f"[DB IntegrityError] {e.orig}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflito de integridade no banco de dados.",
        ) from e
    
    except SQLAlchemyError as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno no banco de dados.",
        ) from e
    
    except Exception as e:
        session.rollback()
        raise e