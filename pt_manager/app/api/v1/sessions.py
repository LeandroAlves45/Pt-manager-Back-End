from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import db_session
from app.core.db_errors import commit_or_rollback
from app.db.models.session import TrainingSession
from app.schemas.training_session import TrainingSessionCreate, TrainingSessionRead, TrainingSessionUpdate
from app.services.session_service import SessionService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get("", response_model=list[TrainingSessionRead])
def list_sessions(
    client_id: str | None = None,
    limit: int = 100,
    session: Session = Depends(db_session),
) -> list[TrainingSessionRead]:
    try:
        stmt = select(TrainingSession)

        if client_id:
            stmt = stmt.where(TrainingSession.client_id == client_id)

        stmt = stmt.order_by(TrainingSession.starts_at.desc()).limit(min(limit, 200))

        return session.exec(stmt).all()

    except SQLAlchemyError as e:
        logger.exception("Erro DB ao listar sessões")
        raise HTTPException(status_code=500, detail="Erro ao listar sessões.") from e

@router.post("/clients/{client_id}", response_model=TrainingSessionRead, status_code=status.HTTP_201_CREATED)
def schedule_session_for_client(
    client_id: str,
    payload: TrainingSessionCreate,
    session: Session = Depends(db_session),
) -> TrainingSession:
    """
    Agenda uma nova sessão de treino para um cliente específico.
    """
    try:

        return SessionService.schedule_session(
            session = session,
            client_id=client_id,
            starts_at=payload.starts_at,
            duration_minutes=payload.duration_minutes,
            location=payload.location,
            notes=payload.notes,
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao agendar sessão.") from e  

@router.put("/{session_id}", response_model=TrainingSessionRead)
def update_session(
    session_id: str,
    payload: TrainingSessionUpdate,
    session: Session = Depends(db_session),
) -> TrainingSession:
    """
    Atualiza os detalhes de uma sessão de treino existente.
    """
    try:

        ts = session.get(TrainingSession, session_id)
        if not ts:
            raise ValueError(f"Sessão com ID '{session_id}' não encontrada.")
        
        #starts_at (date)
        if payload.starts_at is not None:
            ts.starts_at = payload.starts_at
        
        #Campos simples
        if payload.duration_minutes is not None:
            ts.duration_minutes = payload.duration_minutes

        if payload.location is not None:
            ts.location = payload.location
        
        if payload.notes is not None:
            ts.notes = payload.notes
        
        if payload.status is not None:
            allowed = {"scheduled","missed", "cancelled"}
            #completed: só via completar sessão
            if payload.status == "completed":
                raise HTTPException(status_code=400, detail="Use o endpoint /complete para marcar a sessão como concluída.")
            
            if payload.status not in allowed:
                raise HTTPException(status_code=400, detail=f"Status inválido. Valores permitidos: {allowed}")
                        
            ts.status = payload.status
        session.add(ts)
        commit_or_rollback(session)
        session.refresh(ts)
        return ts

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao atualizar sessão.") from e


@router.post("/{session_id}/missed", status_code=status.HTTP_200_OK, response_model=TrainingSessionRead)
def mark_session_missed(
    session_id: str,
    session: Session = Depends(db_session),
) -> TrainingSession:
    """
    Marca a sessão como 'missed' (cliente faltou).
    Mantém histórico (não apaga).
    """
    try:
        ts = session.get(TrainingSession, session_id)
        if not ts:
            raise HTTPException(status_code=404, detail="Sessão não encontrada.")

        ts.status = "missed"

        session.add(ts)
        commit_or_rollback(session)
        session.refresh(ts)
        return ts

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao marcar falta.") from e

@router.post("/{session_id}/complete", response_model=TrainingSessionRead)
def complete_session(session_id: str, session: Session = Depends(db_session)) -> TrainingSession:
    """
    Marca uma sessão como concluída e consome um pack do cliente.
    """
    try:
        return SessionService.complete_session_consuming_pack(session=session, session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao completar sessão.") from e