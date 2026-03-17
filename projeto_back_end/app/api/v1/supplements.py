"""
Router de suplementação — CRUD completo com controlo de acesso por role.

Acesso:
    Trainers : CRUD completo (criar, ler, atualizar, arquivar, apagar)
    Clients  : apenas leitura dos suplementos ativos (sem trainer_notes)

Endpoints:
    GET    /supplements              — lista suplementos do trainer autenticado
    POST   /supplements              — criar suplemento (trainer only)
    GET    /supplements/{id}         — detalhe de um suplemento
    PATCH  /supplements/{id}         — atualizar suplemento (trainer only)
    POST   /supplements/{id}/archive   — arquivar (trainer only)
    POST   /supplements/{id}/unarchive — reativar (trainer only)
    DELETE /supplements/{id}         — apagar permanentemente (trainer only)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select

from app.api.deps import db_session
from app.core.security import get_current_user, require_trainer
from app.core.db_errors import commit_or_rollback
from app.db.models.supplement import Supplement
from app.schemas.supplement import (
    SupplementCreate,
    SupplementReadPublic,
    SupplementRead,
    SupplementUpdate,
)
from app.utils.time import utc_now_datetime

router = APIRouter(prefix="/supplements", tags=["Supplements"])

#------------------------------
# Helpers
#------------------------------

def _get_supplement_or_404(supplement_id: int, session: Session) -> Supplement:
    """
    Busca um suplemento por ID ou levanta 404 se não existir.
    """
    supplement = session.get(Supplement, supplement_id)
    if not supplement:
        raise HTTPException(status_code=404, detail="Suplemento não encontrado")
    return supplement

def _assert_trainer_owns(supplement: Supplement, trainer_id: str) -> None:
    """
    Verifica se o suplemento pertence ao trainer. Levanta 403 se não.
    """
    if supplement.created_by_user_id != trainer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para modificar este suplemento.")
    

def to_response(supplement: Supplement, user_role: str):
    """
    Devolve SupplementRead (com trainer_notes) para trainers,
    ou SupplementReadPublic (sem trainer_notes) para clientes.

    Esta lógica centraliza a decisão de o que mostrar a cada role,
    evitando repetição em cada endpoint.
    """
    if user_role in ["trainer", "superuser"]:
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
    
    #Lista suplementos. Por default, apenas ativos. Trainers podem incluir arquivados.
    # Personal Trainer vê apenas os suplementos que criou ou já criados pelo superuser.

    query = select(Supplement)
    
    if current_user.role in {"trainer", "superuser"}:
        # Trainers veem seus suplementos + suplementos do superuser
        query = query.where(
            (Supplement.created_by_user_id == current_user.id) | 
            (Supplement.created_by_user_id == "superuser")
        )
        if not include_archived:
            query = query.where(Supplement.archived_at.is_(None))
    else:
        # Clientes nunca veem suplementos arquivados
        query = query.where(Supplement.archived_at.is_(None))

    query = query.order_by(Supplement.name)
    supplements = session.exec(query).all()
    return [to_response(s, current_user.role) for s in supplements]

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_supplement(
    payload: SupplementCreate,
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer), #apenas trainers podem criar
) -> SupplementRead:

    # Cria um novo suplemento no catalogo do Personal Trainer autenticado.
    # O campo created_by_user_id é preenchido automaticamente com o ID do Personal Trainer.

    try:
        supplement = Supplement(
            **payload.model_dump(),
            created_by_user_id=current_user.id, #regista quem criou
        )
        session.add(supplement)
        commit_or_rollback(session)
        session.refresh(supplement)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Erro ao criar suplemento: ") from e

    return SupplementRead.model_validate(supplement)

@router.get("/{supplement_id}")
async def get_supplement(
    supplement_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user), 
):
    # Detalhes de um suplemento. Trainers veem tudo, clientes veem apenas suplementos ativos.
    try:
        supplement = _get_supplement_or_404(supplement_id, session)

        if not supplement:
            raise HTTPException(status_code=404, detail="Suplemento não encontrado")

        if current_user.role == "client" and supplement.archived_at is not None:
            raise HTTPException(status_code=404, detail="Acesso negado a suplemento arquivado")
    except HTTPException:
        raise   
    except Exception as e:
        raise HTTPException(status_code=400, detail="Erro ao buscar suplemento: ") from e
    
    return to_response(supplement, current_user.role)

@router.patch("/{supplement_id}", response_model=SupplementRead)
async def update_supplement(
    supplement_id: str,
    payload: SupplementUpdate,
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer), #apenas trainers podem atualizar
) -> SupplementRead:

    #Atualiza um suplemento. Apenas o Personal Trainer que criou o suplemento ou o superuser podem atualizar.

    try:
        supplement = _get_supplement_or_404(supplement_id, session)
        _assert_trainer_owns(supplement, current_user.id)


        if not supplement:
            raise HTTPException(status_code=404, detail="Suplemento não encontrado")

        #model_dump(exclude_unset=True) devolve apenas os campos que foram enviados no payload, permitindo atualizações parciais
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(supplement, key, value)

        supplement.updated_at = utc_now_datetime() #regista quando foi atualizado
        session.add(supplement) 
        commit_or_rollback(session)
        session.refresh(supplement)

    except Exception as e:
        raise HTTPException(status_code=400, detail="Erro ao atualizar suplemento: ") from e

    return SupplementRead.model_validate(supplement)

@router.post("/{supplement_id}/archive", response_model=SupplementRead)
async def archive_supplement(
    supplement_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer), 
) -> SupplementRead:

    # Arquiva um suplemento (soft-delete). Apenas o Personal Trainer que criou o suplemento ou o superuser podem arquivar.

    try:
        supplement = _get_supplement_or_404(supplement_id, session)
        _assert_trainer_owns(supplement, current_user.id)

        if not supplement:
            raise HTTPException(status_code=404, detail="Suplemento não encontrado")
   

        if supplement.archived_at is not None:
            return SupplementRead.model_validate(supplement) #já arquivado, não faz nada
    
        supplement.archived_at = utc_now_datetime() #regista quando foi arquivado
        supplement.updated_at = utc_now_datetime() #regista quando foi atualizado
        session.add(supplement)
    
        commit_or_rollback(session)
        session.refresh(supplement)
    except Exception as e:
           raise HTTPException(status_code=400, detail="Erro ao atualizar data de arquivamento: ") from e

    return SupplementRead.model_validate(supplement)

@router.post("/{supplement_id}/unarchive", response_model=SupplementRead)
async def unarchive_supplement(
    supplement_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer), 
) -> SupplementRead:
    
    #Reativa um suplemento arquivado. Apenas o Personal Trainer que criou o suplemento ou o superuser podem reativar.
    
    try:

        supplement = _get_supplement_or_404(supplement_id, session)
        _assert_trainer_owns(supplement, current_user.id)

        if not supplement:
            raise HTTPException(status_code=404, detail="Suplemento não encontrado")

        if supplement.archived_at is not None:
            supplement.archived_at = None #remove data de arquivamento para reativar
            supplement.updated_at = utc_now_datetime() #regista quando foi atualizado
            session.add(supplement)
       
            commit_or_rollback(session)
            session.refresh(supplement)
    except Exception as e:
            raise HTTPException(status_code=400, detail="Erro ao reativar suplemento: ") from e

    return SupplementRead.model_validate(supplement)

@router.delete("/{supplement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplement(
    supplement_id: int,
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer), #apenas trainers podem apagar
):

    # Apaga permanentemente um suplemento. Apenas o Personal Trainer que criou o suplemento ou o superuser podem apagar.
    try:
        supplement = _get_supplement_or_404(supplement_id, session)
        _assert_trainer_owns(supplement, current_user.id)

        if not supplement:
            raise HTTPException(status_code=404, detail="Suplemento não encontrado")

        session.delete(supplement)
        commit_or_rollback(session)

    except Exception as e:
        raise HTTPException(status_code=400, detail="Erro ao apagar suplemento: ") from e