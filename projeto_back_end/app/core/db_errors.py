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

        pg_error = str(e.orig) if e.orig else str(e)
        logger.error("[DB IntegrityError] %s", pg_error)

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Conflito de integridade: {pg_error}",
        ) from e
    
    except SQLAlchemyError as e:
        session.rollback()
        logger.error("[DB SQLAlchemyError] %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno no banco de dados.",
        ) from e
 
    except Exception as e:
        session.rollback()
        raise e