from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import db_session
from app.core.security import require_active_subscription
from app.core.db_errors import commit_or_rollback
from app.db.models.session import TrainingSession
from app.db.models.client import Client
from app.schemas.training_session import TrainingSessionCreate, TrainingSessionRead, TrainingSessionUpdate
from app.services.sessions import SessionService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get("", response_model=list[TrainingSessionRead])
async def list_sessions(
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
async def schedule_session_for_client(
    client_id: str,
    payload: TrainingSessionCreate,
    session: Session = Depends(db_session),
    current_user=Depends(require_active_subscription)
) -> TrainingSession:
    """
    Agenda uma nova sessão de treino para um cliente específico.
    """
    try:

        #Verificar a modalidade do cliente
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        
        #clientes online não tem sessões presenciais
        if client.training_modality == "online":
            raise HTTPException(status_code=400, detail="Cliente treina online, não pode agendar sessão presencial.")
        
        #verificar ownership
        if current_user.role == "trainer" and client.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Sem permissão para agendar sessão para este cliente.")

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
        # Log técnico completo (stacktrace)
        logger.exception("Erro ao agendar sessão no banco de dados")

        raise HTTPException(status_code=500, detail=str(e)) from e  

@router.put("/{session_id}", response_model=TrainingSessionRead)
async def update_session(
    session_id: str,
    payload: TrainingSessionUpdate,
    session: Session = Depends(db_session),
) -> TrainingSession:
    
    #Atualiza os detalhes de uma sessão de treino existente.

    try:
        
        if payload.status == "completed":
                raise HTTPException(status_code=400, detail="Use o endpoint /complete para marcar a sessão como concluída.")

        #valida status (se fornecido)    
        if payload.status is not None:
            allowed_statuses = {"scheduled", "missed", "cancelled"}
            if payload.status not in allowed_statuses:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Status inválido. Valores permitidos: {allowed_statuses}"
                )
            
        #delegação 

        updated_session = SessionService.update_session(
            session=session,
            session_id=session_id,
            starts_at=payload.starts_at,
            duration_minutes=payload.duration_minutes,
            location=payload.location,
            notes=payload.notes,
            status=payload.status
        )
        return updated_session

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    except SQLAlchemyError as e:
         # Erros de banco de dados
        logger.exception("Erro ao atualizar sessão")
        raise HTTPException(
            status_code=500, 
            detail="Erro ao atualizar sessão."
        ) from e


@router.post("/{session_id}/missed", status_code=status.HTTP_200_OK, response_model=TrainingSessionRead)
async def mark_session_missed(
    session_id: str,
    session: Session = Depends(db_session),
) -> TrainingSession:
    #Marca a sessão como 'missed' (cliente faltou).
    #Mantém histórico (não apaga). Não consome pack, apenas sinaliza que a sessão foi perdida.

    try:
        # Delegação ao SessionService
        return SessionService.mark_session_missed(
            session=session,
            session_id=session_id
        )

    except ValueError as e:
        # Erros de validação de negócio
        raise HTTPException(status_code=400, detail=str(e)) from e
    
    except SQLAlchemyError as e:
        # Erros de banco de dados
        logger.exception("Erro ao marcar falta")
        raise HTTPException(status_code=500, detail="Erro ao marcar falta.") from e

@router.post("/{session_id}/complete", response_model=TrainingSessionRead)
async def complete_session(session_id: str, session: Session = Depends(db_session)) -> TrainingSession:
    """
    Marca uma sessão como concluída e consome um pack do cliente.
    """
    try:
        return SessionService.complete_session_consuming_pack(session=session, session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao completar sessão.") from e
    
#endpoint para cancelar sessão
@router.post("/{session_id}/cancel", response_model=TrainingSessionRead)
async def cancel_session(session_id: str, session: Session = Depends(db_session)) -> TrainingSession:
    
    #Cancela uma sessão de treino.
    # - Se a sessão for cancelada, notificações futuras relacionadas a ela serão canceladas.
    # - O cliente pode reagendar posteriormente, criando uma nova sessão.
    
    try:
        return SessionService.cancel_session(session=session, session_id=session_id)
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao cancelar sessão.") from e