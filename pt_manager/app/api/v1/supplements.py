"""
Router de suplementação — CRUD completo com controlo de acesso por role.

Acesso:
    Trainers : CRUD completo (criar, ler, atualizar, arquivar, apagar)
    Clients  : apenas leitura dos suplementos ativos (sem trainer_notes)

Endpoints:
    GET    /supplements          — lista suplementos (ativos por default)
    POST   /supplements          — criar suplemento (trainer only)
    GET    /supplements/{id}     — detalhe de um suplemento
    PATCH  /supplements/{id}     — atualizar suplemento (trainer only)
    POST   /supplements/{id}/archive   — arquivar (trainer only)
    POST   /supplements/{id}/unarchive — reativar (trainer only)
    DELETE /supplements/{id}     — apagar permanentemente (trainer only)
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select

from app.api.deps import db_session
from app.core.security import get_current_user, require_trainer
from app.db.models.supplement import Supplement
from app.schemas.supplement import (
    SupplementCreate,
    SupplementReadPublic,
    SupplementRead,
    SupplementUpdate,
)

router = APIRouter(prefix="/supplements", tags=["Supplements"])

#------------------------------
# Helpers
#------------------------------

def to_response(supplement: Supplement, user_role: str):
    """
    Devolve SupplementRead (com trainer_notes) para trainers,
    ou SupplementReadPublic (sem trainer_notes) para clientes.

    Esta lógica centraliza a decisão de o que mostrar a cada role,
    evitando repetição em cada endpoint.
    """
    if user_role == "trainer":
        return SupplementRead.model_validate(supplement)
    else:
        return SupplementReadPublic.model_validate(supplement)
    
#------------------------------
# Endpoints
#------------------------------

@router.get("")
async def list_supplements(
    include_archived: bool = Query(False, description="Incluir suplementos arquivados"),
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user), #qualquer utilizador autenticado pode listar
):
    """
    Lista suplementos. Por default, apenas ativos. Trainers podem incluir arquivados.
    """

    query = select(Supplement)
    if not include_archived or current_user.role == "trainer":
        query = query.where(Supplement.archived_at.is_(None))

    #ordena por nome
    query = query.order_by(Supplement.name)
    
    supplements = session.exec(query).all()
    return [to_response(s, current_user.role) for s in supplements]

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_supplement(
    payload: SupplementCreate,
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer), #apenas trainers podem criar
) -> SupplementRead:
    """
    Cria um novo suplemento. Apenas trainers podem criar.
    """

    supplement = Supplement(
        **payload.model_dump(),
        created_by_user_id=current_user.id, #regista quem criou
    )
    session.add(supplement)

    try:
        session.commit()
        session.refresh(supplement)
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail="Erro ao criar suplemento: ") from e

    return SupplementRead.model_validate(supplement)

@router.get("/{supplement_id}")
async def get_supplement(
    supplement_id: int,
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user), #qualquer utilizador autenticado pode ver detalhes
):
    """
    Detalhes de um suplemento. Trainers veem tudo, clientes veem apenas suplementos ativos.
    """

    supplement = session.get(Supplement, supplement_id)
    if not supplement:
        raise HTTPException(status_code=404, detail="Suplemento não encontrado")

    if current_user.role == "client" and supplement.archived_at is not None:
        raise HTTPException(status_code=404, detail="Acesso negado a suplemento arquivado")

    return to_response(supplement, current_user.role)

@router.patch("/{supplement_id}", response_model=SupplementRead)
async def update_supplement(
    supplement_id: int,
    payload: SupplementUpdate,
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer), #apenas trainers podem atualizar
) -> SupplementRead:
    """
    Atualiza um suplemento. Apenas trainers podem atualizar.
    """

    supplement = session.get(Supplement, supplement_id)
    if not supplement:
        raise HTTPException(status_code=404, detail="Suplemento não encontrado")

    #model_dump(exclude_unset=True) devolve apenas os campos que foram enviados no payload, permitindo atualizações parciais
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(supplement, key, value)

    supplement.updated_at = datetime.utcnow() #regista quando foi atualizado
    session.add(supplement) 

    try:
        session.commit()
        session.refresh(supplement)
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail="Erro ao atualizar suplemento: ") from e

    return SupplementRead.model_validate(supplement)

@router.post("/{supplement_id}/archive", response_model=SupplementRead)
async def archive_supplement(
    supplement_id: int,
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer), #apenas trainers podem arquivar
) -> SupplementRead:
    """
    Arquiva um suplemento. Apenas trainers podem arquivar.
    """

    supplement = session.get(Supplement, supplement_id)
    if not supplement:
        raise HTTPException(status_code=404, detail="Suplemento não encontrado")

    if supplement.archived_at is not None:
        supplement.archived_at = datetime.utcnow() #atualiza data de arquivamento
        supplement.updated_at = datetime.utcnow() #regista quando foi atualizado
        session.add(supplement)
        try:
            session.commit()
            session.refresh(supplement)
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=400, detail="Erro ao atualizar data de arquivamento: ") from e

    return SupplementRead.model_validate(supplement)

@router.post("/{supplement_id}/unarchive", response_model=SupplementRead)
async def unarchive_supplement(
    supplement_id: int,
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer), #apenas trainers podem reativar
) -> SupplementRead:
    """
    Reativa um suplemento arquivado. Apenas trainers podem reativar.
    """

    supplement = session.get(Supplement, supplement_id)
    if not supplement:
        raise HTTPException(status_code=404, detail="Suplemento não encontrado")

    if supplement.archived_at is not None:
        supplement.archived_at = None #remove data de arquivamento
        supplement.updated_at = datetime.utcnow() #regista quando foi atualizado
        session.add(supplement)
        try:
            session.commit()
            session.refresh(supplement)
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=400, detail="Erro ao reativar suplemento: ") from e

    return SupplementRead.model_validate(supplement)

@router.delete("/{supplement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplement(
    supplement_id: int,
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer), #apenas trainers podem apagar
):
    """
    Apaga permanentemente um suplemento. Apenas trainers podem apagar.
    """

    supplement = session.get(Supplement, supplement_id)
    if not supplement:
        raise HTTPException(status_code=404, detail="Suplemento não encontrado")

    session.delete(supplement)

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail="Erro ao apagar suplemento: ") from e