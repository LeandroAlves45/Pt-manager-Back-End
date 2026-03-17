"""
CRUD para avaliações iniciais (InitialAssessment).
 
Esta camada trata exclusivamente do acesso à base de dados.
Nunca lança HTTPException — isso é responsabilidade dos routers.
 
Diferença entre os dois tipos de avaliação:
    InitialAssessment — formulário de saúde completo, feito uma vez pelo trainer
    CheckIn           — check-in periódico de progresso, pode ser preenchido pelo cliente
    Este ficheiro trata apenas do InitialAssessment.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, select
from app.db.models.initial_assessment import InitialAssessment
from app.schemas.initial_assessment import InitialAssessmentCreate, InitialAssessmentUpdate

def get_initial_assessment_by_id(session: Session, assessment_id: str) -> Optional[InitialAssessment]:
    """Devolve uma avaliação inicial pelo seu ID, ou None se não existir."""
    return session.get(InitialAssessment, assessment_id)

def list_initial_assessments_by_client(session: Session, client_id: str) -> List[InitialAssessment]:
    """
    Lista todas as avaliações iniciais de um cliente, ordenadas da mais recente.
    Um cliente pode ter mais do que uma avaliação inicial ao longo do tempo.
    """
    statement = (
        select(InitialAssessment)
        .where(InitialAssessment.client_id == client_id)
        .order_by(InitialAssessment.created_at.desc()) 
    )

    return session.exec(statement).all()

def count_initial_assessments_by_client(session: Session, client_id: str) -> int:
    """
    Conta o número de avaliações iniciais de um cliente.
    Usado para determinar se é a primeira avaliação (lógica de negócio no router).
    """
    statement = select(InitialAssessment).where(InitialAssessment.client_id == client_id)
    return len(session.exec(statement).all())

def create_initial_assessment(
    session: Session,
    payload: InitialAssessmentCreate,
    trainer_id: str) -> InitialAssessment:
    """
    Cria uma nova avaliação inicial para um cliente.
 
    O health_questionnaire é serializado para dict antes de persistir
    — o campo no modelo é JSONB, aceita dict directamente.
    """
    #Serializa o questionário Pydantic para dict (JSONB no postregesql)
    queationnaire_dict = None
    if payload.health_questionnaire:
        queationnaire_dict = payload.health_questionnaire.model_dump(exclude_none=True)

    #Cria o registo principal da avaliação
    assessment = InitialAssessment(
        client_id=payload.client_id,
        assessed_by_trainer_id=trainer_id,
        weight_kg=payload.weight_kg,
        height_cm=payload.height_cm,
        body_fat=payload.body_fat,
        health_questionnaire=queationnaire_dict,
        notes=payload.notes,
    )
    session.add(assessment)

def update_initial_assessment(session: Session, assessment: InitialAssessment, payload: InitialAssessmentUpdate) -> InitialAssessment:
    """
    Actualiza campos de uma avaliação inicial existente (PATCH parcial).
    Apenas os campos enviados no payload são alterados.
    """
    data = payload.model_dump(exclude_unset=True)

    if "health_questionnaire" in data and data["health_questionnaire"] is not None:
        data["health_questionnaire"] = payload.health_questionnaire.model_dump(exclude_none=True)

    
    for key, value in data.items():
        setattr(assessment, key, value)

    assessment.updated_at = datetime.now(timezone.utc)
    session.add(assessment)
    return assessment

