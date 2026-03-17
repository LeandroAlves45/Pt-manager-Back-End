"""
Router de avaliações iniciais — InitialAssessment.
 
Estes endpoints gerem o formulário de saúde completo preenchido pelo trainer
na primeira (ou ocasional) consulta com o cliente.
 
Diferença para os check-ins:
    /assessments → InitialAssessment: historial médico, biometria, objetivos
    /checkins    → CheckIn: progresso periódico, preenchido pelo cliente
 
Endpoints:
    POST   /assessments/              — criar avaliação inicial
    GET    /assessments/client/{id}   — listar avaliações de um cliente
    GET    /assessments/{id}          — detalhe de uma avaliação
    PATCH  /assessments/{id}          — actualizar avaliação
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session
from typing import List

from app.api.deps import db_session
from app.core.security import require_active_subscription
from app.core.db_errors import commit_or_rollback
from app.db.models.client import Client
import app.crud.assessment as crud
from app.schemas.initial_assessment import (
    InitialAssessmentCreate,
    InitialAssessmentRead,
    InitialAssessmentUpdate,
)

router = APIRouter(prefix="/assessments", tags=["Assessments"])


# ============================================================
# POST /assessments/ — criar avaliação inicial
# ============================================================

@router.post("/", response_model=InitialAssessmentRead, status_code=status.HTTP_201_CREATED)
def create_assessment(
    payload: InitialAssessmentCreate,
    session: Session = Depends(db_session),
    current_user=Depends(require_active_subscription),
) -> InitialAssessmentRead:
    # Cria uma avaliação inicial para um cliente do Personal Trainer autenticado.
    # Verifica se o cliente pertence ao trainer.

    # Verifica se o cliente existe e pertence ao trainer
    client = session.get(Client, payload.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    
    if client.owner_trainer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cliente não pertence ao Personal Trainer autenticado.")
    
    if client.archived_at:
        raise HTTPException(status_code=400, detail="Cliente está arquivado. Não é possível criar avaliação para um cliente arquivado.")
    
    # Cria a avaliação inicial
    try:
        assessment = crud.create_initial_assessment(session, payload, trainer_id=current_user.id)
        commit_or_rollback(session)
        session.refresh(assessment)

        return InitialAssessmentRead.model_dump(assessment)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro inesperado ao criar avaliação inicial.") from e
    
# ============================================================
# GET /assessments/client/{client_id} — listar avaliações de um cliente
# ============================================================

@router.get("/client/{client_id}", response_model=List[InitialAssessmentRead])
def list_assessments_by_client(
    client_id: str,
    session: Session = Depends(db_session),
    current_user=Depends(require_active_subscription),
) -> List[InitialAssessmentRead]:
    #Lista todas as avaliações fisicas de um cliente, ordenadas da mais recente para a mais antiga. 
    
    try:
        #Verifica se o cliente pertence ao trainer autenticado
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        if client.owner_trainer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Cliente não pertence ao Personal Trainer autenticado.")
        
        #Busca as avaliações físicas do cliente
        assessments = crud.list_initial_assessments_by_client(session, client_id)

        #Constrói a lista de schemas de leitura para resposta
        return [InitialAssessmentRead.model_validate(a) for a in assessments]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro inesperado ao listar avaliações físicas do cliente.") from e
    

# ============================================================
# GET /assessments/{assessment_id} — detalhe de uma avaliação
# ============================================================

@router.get("/{assessment_id}", response_model=InitialAssessmentRead)
def get_assessment(
    assessment_id: int, 
    session: Session = Depends(db_session),
    current_user=Depends(require_active_subscription),
) -> InitialAssessmentRead:
    #Obtém os detalhes de uma avaliação física específica pelo seu ID. 

    try:
        assessment = crud.get_initial_assessment_by_id(session, assessment_id)
        if not assessment:
            raise HTTPException(status_code=404, detail="Avaliação física não encontrada.")
        
        client = session.get(Client, assessment.client_id)
        if not client or client.owner_trainer_id != current_user.id:
            raise HTTPException(status_code=403, detail="A avaliação física não pertence ao Personal Trainer autenticado.")
        
        return InitialAssessmentRead.model_validate(assessment)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro inesperado ao obter avaliação física.") from e
    
# ============================================================
# PATCH /assessments/{assessment_id} — actualizar avaliação
# ============================================================
@router.patch("/{assessment_id}", response_model=InitialAssessmentRead)
def update_assessment(
    assessment_id: str, 
    payload: InitialAssessmentUpdate,
    session: Session = Depends(db_session),
    current_user=Depends(require_active_subscription),
) -> InitialAssessmentRead:
    # Atualiza os campos de uma avaliação física existente. Apenas os campos enviados no payload são alterados (PATCH parcial).

    try:
        assessment = crud.get_initial_assessment_by_id(session, assessment_id)
        if not assessment:
            raise HTTPException(status_code=404, detail="Avaliação física não encontrada.")
        
        # Verificação do tenant do cliente e do trainer
        client = session.get(Client, assessment.client_id)
        if not client or client.owner_trainer_id != current_user.id:
            raise HTTPException(status_code=403, detail="A avaliação física não pertence ao Personal Trainer autenticado.")
        
        assessment = crud.update_initial_assessment(session, assessment, payload)
        commit_or_rollback(session)
        session.refresh(assessment)

        return InitialAssessmentRead.model_validate(assessment)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro inesperado ao atualizar avaliação física.") from e