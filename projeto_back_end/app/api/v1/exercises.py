"""
Router de exercícios — catálogo global + privado por trainer.
 
Regras de negócio:
  - Exercícios com owner_trainer_id = None são GLOBAIS: visíveis a todos os trainers,
    editáveis apenas pelo superuser via /admin/exercicios.
  - Exercícios com owner_trainer_id = <uuid> são PRIVADOS do trainer.
  - Trainers só podem criar, editar e apagar os SEUS exercícios privados.
  - Na listagem, o trainer vê os seus privados + todos os globais.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional

from app.api.deps import db_session
from app.core.security import get_current_user, require_trainer
from app.core.db_errors import commit_or_rollback
from app.db.models.training import Exercise
from app.schemas.training import ExerciseCreate, ExerciseRead, ExerciseUpdate
from app.utils.time import utc_now

router = APIRouter(prefix="/exercises", tags=["Exercises"])

# ===================================================
# HELPERS
# ===================================================


def _to_read(e: Exercise) -> ExerciseRead:
    return ExerciseRead(
        id=e.id,
        name=e.name,
        muscles=e.muscles,
        url=e.url,
        is_active=e.is_active,
        owner_trainer_id=e.owner_trainer_id,
        created_at=e.created_at,
        updated_at=e.updated_at
    )

def _assert_owner(exercise: Exercise, trainer_id: str) -> None:
    """
    Verifica se o exercício pertence ao trainer autenticado.
    Levanta 403 se não pertencer.
 
    Nota: exercícios globais (owner_trainer_id = None) nunca passam nesta
    verificação — são bloqueados antes desta função ser chamada.
    """
    if exercise.owner_trainer_id != trainer_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este exercício.")
    

# =============================================================================
# Endpoints
# =============================================================================

#get de todos os exercicios
@router.get("/", response_model=List[ExerciseRead])
async def list_exercises(
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user),
    q : Optional[str] = Query(default=None, description = "Filtro por nome"),
    only_active: bool = Query(default=False, description="Retorna apenas exercicios ativos"),
    page_size: Optional[int] = Query(default=None, ge=1, le=1000),
    page_number: Optional[int] = Query(default=None, ge=1),
) -> List[ExerciseRead]:
    #Lista exercícios visíveis para o trainer autenticado:
    #  - Todos os exercícios globais (owner_trainer_id IS NULL)
    #  - Os exercícios privados DO trainer autenticado
 
    #Esta query garante isolamento cross-tenant: o trainer A nunca vê os
    #exercícios privados do trainer B.
    
    stmt = select(Exercise).where(
        (Exercise.owner_trainer_id.is_(None)) | (Exercise.owner_trainer_id == current_user.id)
    )


    #validação de filtros
    if only_active:
        stmt = stmt.where(Exercise.is_active == True)
    
    if q:
        stmt = stmt.where(Exercise.name.ilike(f"%{q.strip()}%"))

     #paginação
    if (page_size is None) ^ (page_number is None):
        raise HTTPException(
            status_code=400, 
            detail="Page_size e Page_number devem ser fornecidos juntos para paginação."
        )
    
    # Aplicar paginação APENAS se ambos os parâmetros foram fornecidos
    if page_size is not None and page_number is not None:
        offset = (page_number - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

    try:
        rows = session.exec(stmt).all()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao listar os exercicios.") from e

    return [_to_read(r) for r in rows]

#criação de novo exercicio
@router.post("/", response_model=ExerciseRead, status_code=status.HTTP_201_CREATED)
async def create_exercise(
    payload: ExerciseCreate,
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user),
) -> ExerciseRead:

    #Cria um exercício privado para o trainer autenticado.
    #owner_trainer_id é sempre preenchido com o ID do trainer — nunca fica None.
    #Exercícios globais são criados apenas pelo superuser via /admin/exercicios.

    try:
        #verifica se ja existe exercicio com mesmo nome
        new_exercise = Exercise(
            name=payload.name.strip(),
            muscles=payload.muscles.strip(),
            url=payload.url.strip() if payload.url else None,
            is_active=payload.is_active,
            owner_trainer_id=current_user.id
        )

        session.add(new_exercise)
        commit_or_rollback(session)
        session.refresh(new_exercise)
        return _to_read(new_exercise)
    
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao criar novo exercicio.") from e


#atualização de exercicio
@router.put("/{exercise_id}", response_model=ExerciseRead)
async def update_exercise(
    exercise_id: str,
    payload: ExerciseUpdate,
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user),
) -> ExerciseRead:
    
    #Actualiza um exercício privado do trainer autenticado.
    #Exercícios globais (owner_trainer_id = None) não podem ser editados aqui.
    
    try:
        exercise = session.get(Exercise, exercise_id)
        if not exercise:
            raise HTTPException(status_code=404, detail="Exercicio nao encontrado.")

        if exercise.owner_trainer_id is None:
            raise HTTPException(status_code=403, detail="Exercicio global nao pode ser editado aqui.")
        
        # Verifica se o exercício pertence ao trainer autenticado
        _assert_owner(exercise, current_user.id)

        #atualiza campos se fornecidos
        if payload.name is not None:
            exercise.name = payload.name.strip()
        if payload.muscles is not None:
            exercise.muscles = payload.muscles.strip()
        if payload.url is not None:
            exercise.url = payload.url.strip() if payload.url else None
        if payload.is_active is not None:
            exercise.is_active = payload.is_active

        exercise.updated_at = utc_now()

        session.add(exercise)
        commit_or_rollback(session)
        session.refresh(exercise)
        return _to_read(exercise)

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao atualizar exercicio.") from e
    
#delete exercicio
@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exercise(
    exercise_id: str, 
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user),
) -> None:
    
    #Apaga permanentemente um exercício privado do trainer autenticado.
    #Exercícios globais não podem ser apagados aqui.
    
    try:
        exercise = session.get(Exercise, exercise_id)
        if not exercise:
            raise HTTPException(status_code=404, detail="Exercicio não encontrado.")

        # Bloqueia remoção de exercícios globais neste endpoint
        if exercise.owner_trainer_id is None:
            raise HTTPException(status_code=403, detail="Exercicio global não pode ser apagado aqui.")
        
        _assert_owner(exercise, current_user.id)

        session.delete(exercise)
        commit_or_rollback(session)
        return None

    except HTTPException:
        raise  # Re-levanta exceções HTTP para serem tratadas pelo FastAPI
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao deletar exercicio.") from e