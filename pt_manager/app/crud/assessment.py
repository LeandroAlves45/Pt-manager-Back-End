"""
CRUD para o sistema de avaliações físicas.

Esta camada separa a lógica de acesso a dados dos routers
Os routers tratam de HTTP, o crud trata de queries e transações com o banco.

Padrão:
- Recebe Session e schemas validados
-Devolve modelos ORM 
-Nunca levanta HTTPException - isso é responsabilidade dos routers
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, select
from app.db.models.assessment import Assessment, AssessmentMeasurement, AssessmentPhoto
from app.schemas.assessment import AssessmentCreate

def get_assessment_by_id(session: Session, assessment_id: str) -> Optional[Assessment]:
    """
    Recupera uma avaliação física pelo seu ID.
    """
    return session.get(Assessment, assessment_id)

def list_assessments_by_client(session: Session, client_id: str, include_archived: bool = False) -> List[Assessment]:
    """
    Lista todas as avaliações físicas de um cliente específico, ordenadas da mais recente para a mais antiga.
    """
    statement = (
        select(Assessment)
        .where(Assessment.client_id == client_id)
        .order_by(Assessment.created_at.desc()) #ordena da mais recente para a mais antiga
    )
    if not include_archived:
        #Filtra apenas avaliações ativas (não arquivadas)
        statement = statement.where(Assessment.archived_at.is_(None))
    return session.exec(statement).all()

def count_assessments_by_client(session: Session, client_id: str) -> int:
    """
    Conta o número total de avaliações físicas de um cliente, incluindo as arquivadas.
    """
    statement = select(Assessment).where(Assessment.client_id == client_id)
    return len(session.exec(statement).all())

def create_assessment(session: Session, payload: AssessmentCreate) -> Assessment:
    """
    Cria uma nova avaliação física com os seus measurements e fotos numa só transação.
    """
    #Serializa o questionário para JSON
    queationnaire_dict = None
    if payload.questionnaire:
        queationnaire_dict = payload.questionnaire.model_dump(exclude_none=True)

    #Cria o registo principal da avaliação
    assessment = Assessment(
        client_id=payload.client_id,
        weight_kg=payload.weight_kg,
        body_fat=payload.body_fat,
        notes=payload.notes,
        questionnaire=queationnaire_dict
    )
    session.add(assessment)

    #Flush gera o ID na sessão sem fazer commit á BD
    #Necessário para usar assessment.id nas tabelas filhas
    session.flush()

    #Cria os registos de measurements
    for m in payload.measurements:
        measurement = AssessmentMeasurement(
            assessment_id=assessment.id,
            measurement_type=m.measurement_type,
            value=m.value
        )
        session.add(measurement)

    #Cria os registos de photos
    for p in payload.photos:
        photo = AssessmentPhoto(
            assessment_id=assessment.id,
            photo_type=p.photo_type,
            url=p.url
        )
        session.add(photo)
    
    return assessment

def soft_delete_assessment(session: Session, assessment: Assessment) -> Assessment:
    """
    Arquiva uma avaliação física (soft delete) definindo a data de arquivamento.
    """
    assessment.archived_at = datetime.now(timezone.utc)
    assessment.updated_at = datetime.now(timezone.utc)
    session.add(assessment)
    return assessment

def get_measurements_by_assessment(session: Session, assessment_id: str) -> List[AssessmentMeasurement]:
    """
    Lista todos os perímetros corporais de uma avaliação física específica.
    """
    statement = select(AssessmentMeasurement).where(AssessmentMeasurement.assessment_id == assessment_id)
    return session.exec(statement).all()

def get_photos_by_assessment(session: Session, assessment_id: str) -> List[AssessmentPhoto]:
    """
    Lista todas as fotos de progresso de uma avaliação física específica.
    """
    statement = select(AssessmentPhoto).where(AssessmentPhoto.assessment_id == assessment_id)
    return session.exec(statement).all()