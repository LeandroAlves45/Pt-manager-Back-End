"""
Router para o sistema de avaliações físicas

Endpoints:
- POST /assessments/ : Criar uma nova avaliação física
- GET /assessments/client/{client_id} : Listar todas as avaliações físicas do usuário
- GET /assessments/{assessment_id} : Obter detalhes de uma avaliação física específica
- DELETE /assessments/{assessment_id} : Excluir uma avaliação física específica

Regra de negócio:   
- Primeira avaliação de um cliente: campo 'injuries' no queationário de avaliação física é obrigatório.
- Avaliações arquivadas não aparecem na listagem por defeito.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List

from app.api.deps import db_session
from app.core.db_errors import commit_or_rollback
from app.db.models.client import Client
import app.crud.assessment as crud
from app.schemas.assessment import (
    AssessmentCreate,
    AssessmentRead,
    MeasurementRead,
    PhotoRead,
)

router = APIRouter(prefix="/assessments", tags=["Assessments"])

#----------------------------------------------
#Helpers
#----------------------------------------------

def _build_assessment_read(session: Session, assessment) -> AssessmentRead:
    #Constrói o schema de leitura de avaliação física, incluindo medidas e fotos.
    measurements = crud.get_measurements_by_assessment_id(session, assessment.id)
    photos = crud.get_photos_by_assessment_id(session, assessment.id)

    return AssessmentRead(
        id=assessment.id,
        client=assessment.client_id,
        weight_kg=assessment.weight_kg,
        body_fat=assessment.body_fat,
        notes=assessment.notes,
        questionnaire=assessment.questionnaire,
        measurements=[
            MeasurementRead(
                id=m.id,
                measurement_type=m.type,
                value=m.value,
            ) 
            for m in measurements
        ],
        photos=[
            PhotoRead(
                id=p.id,
                photo_type=p.type,
                url=p.url,
            )
            for p in photos
        ],
        archived_at=assessment.archived_at,
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


#---------------------------------------------
#POST /assessments/ - Criar avaliação física
#---------------------------------------------

@router.post("/", response_model=AssessmentRead, status_code=status.HTTP_201_CREATED)
def create_assessment(
    payload: AssessmentCreate,
    session: Session = Depends(db_session),
) -> AssessmentRead:
    try:
        #Verifica se o cliente existe
        client = session.get(Client, payload.client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        #Verifica se o cliente está arquivado
        if client.archived_at:
            raise HTTPException(status_code=400, detail="Não é possível criar avaliação para cliente arquivado.")
        
        #Primeira avaliação de um cliente: campo 'injuries' no questionário é obrigatório.
        is_first_assessment = crud.count_assessments_by_client_id(session, payload.client_id) == 0
        if is_first_assessment:
            if not payload.questionnaire or not payload.questionnaire.injuries:
                raise HTTPException(
                    status_code=400, 
                    detail="Para a primeira avaliação de um cliente, o campo 'injuries' no questionário é obrigatório."
                )

        #Cria a avaliação física
        assessment = crud.create_assessment(session, payload)
        commit_or_rollback(session)
        session.refresh(assessment)

        #Constrói o schema de leitura para resposta
        return _build_assessment_read(session, assessment)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro de base de dados ao criar avaliação física.") from e
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao criar avaliação física.") from e
    
#---------------------------------------------
#GET /assessments/client/{client_id} - Listar avaliações físicas de um cliente
#---------------------------------------------

@router.get("/client/{client_id}", response_model=List[AssessmentRead])
def list_assessments_by_client(
    client_id: str,
    include_archived: bool = Query(default=False, description="Incluir avaliações arquivadas na resposta"),
    session: Session = Depends(db_session),
) -> List[AssessmentRead]:
    #Lista todas as avaliações fisicas de um cliente, ordenadas da mais recente para a mais antiga. Por defeito, avaliações arquivadas não são incluídas na resposta. Para incluir, use o parâmetro 'include_archived=true'. Avaliações arquivadas são aquelas que foram marcadas como arquivadas (campo 'archived_at' preenchido) e geralmente representam avaliações antigas ou desatualizadas que o profissional deseja manter no sistema para referência, mas não quer que apareçam nas listagens principais.
    try:
        #Verifica se o cliente existe
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        #Busca as avaliações físicas do cliente
        assessments = crud.get_assessments_by_client_id(session, client_id, include_archived=include_archived)

        #Constrói a lista de schemas de leitura para resposta
        return [_build_assessment_read(session, a) for a in assessments]
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro de base de dados ao listar avaliações físicas.") from e
    

#---------------------------------------------
#GET /assessments/{assessment_id} - Obter detalhes de uma avaliação física
#---------------------------------------------

@router.get("/{assessment_id}", response_model=AssessmentRead)
def get_assessment(assessment_id: int, session: Session = Depends(db_session)) -> AssessmentRead:
    #Obtém os detalhes de uma avaliação física específica pelo seu ID. Inclui medidas e fotos associadas.
    try:
        assessment = crud.get_assessment_by_id(session, assessment_id)
        if not assessment:
            raise HTTPException(status_code=404, detail="Avaliação física não encontrada.")
        
        return _build_assessment_read(session, assessment)
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro inesperado ao obter avaliação física.") from e
    
#---------------------------------------------
#DELETE
#---------------------------------------------
@router.delete("/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assessment(assessment_id: int, session: Session = Depends(db_session)) -> None:
    #Soft delete de uma avaliação. Defina 'archived_at'- nao apaga totalmente na BD.
    try:
        assessment = crud.get_assessment_by_id(session, assessment_id)
        if not assessment:
            raise HTTPException(status_code=404, detail="Avaliação física não encontrada.")
        
        if assessment.archived_at:
            raise HTTPException(status_code=400, detail="Avaliação física já está arquivada.")
        
        crud.soft_delete_assessment(session, assessment)
        commit_or_rollback(session)
        return None
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro de base de dados ao arquivar avaliação física.") from e