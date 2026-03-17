"""
Router de atribuicao de suplementos a clientes (SU-04).
 
Permite ao trainer gerir quais suplementos cada cliente deve tomar,
com dose e timing especificos por cliente (podem diferir do catalogo).
 
Acesso:
    Todos os endpoints requerem role=trainer com subscricao activa.
    Multi-tenancy: o trainer so pode gerir clientes e suplementos seus.
 
Endpoints:
    GET    /clients/{client_id}/supplements              — listar suplementos do cliente
    POST   /clients/{client_id}/supplements              — atribuir suplemento ao cliente
    PATCH  /clients/{client_id}/supplements/{assignment_id} — actualizar dose/timing/notas
    DELETE /clients/{client_id}/supplements/{assignment_id} — remover atribuicao
"""
 
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
 
from app.api.deps import db_session
from app.core.security import require_active_subscription
from app.core.db_errors import commit_or_rollback
from app.db.models.client import Client
from app.db.models.supplement import Supplement
from app.db.models.client_supplement import ClientSupplement
from app.schemas.client_supplement import (
    ClientSupplementAssign,
    ClientSupplementUpdate,
    ClientSupplementRead,
)
from app.utils.time import utc_now_datetime
 
router = APIRouter(tags=["Client Supplements"])

# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def _get_client_or_404(client_id: str, trainer_id: str, session: Session) -> Client:
    """
    Busca o cliente e verifica que pertence ao trainer autenticado.
    Lanca 404 se nao existir, 403 se pertencer a outro trainer.
 
    Usar 404 em vez de 403 quando o cliente nao existe evita revelar
    a existencia de clientes de outros trainers (seguranca por obscuridade).
    """

    client = session.get(Client, client_id)
    if not client or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    
    if client.owner_trainer_id != trainer_id:
        raise HTTPException(status_code=403, detail="Sem permissão para acessar este cliente.")
    return client

def _get_supplement_or_404(supplement_id: str, trainer_id: str, session: Session) -> Supplement:
    """
    Busca o suplemento e verifica que pertence ao trainer autenticado.
    Um trainer nao pode atribuir suplementos criados por outro trainer.
    """

    supplement = session.get(Supplement, supplement_id)
    if not supplement or supplement.archived_at is not None:
        raise HTTPException(status_code=404, detail="Suplemento não encontrado.")
    
    if supplement.created_by_user_id != trainer_id:
        raise HTTPException(status_code=403, detail="Sem permissão para acessar este suplemento.")
    return supplement

def _get_assignment_or_404(assignment_id: str, client_id: str, trainer_id: str, session: Session) -> ClientSupplement:
    """
    Busca uma atribuicao especifica e verifica que pertence ao trainer e ao cliente correcto.
    """

    assignment = session.get(ClientSupplement, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Atribuição de suplemento não encontrada.")
    
    if assignment.client_id != client_id or assignment.owner_trainer_id != trainer_id:
        raise HTTPException(status_code=403, detail="Sem permissão para acessar esta atribuição.")
    return assignment

def _build_response(assignment: ClientSupplement, supplement: Supplement) -> ClientSupplementRead:
    """
    Constrói a resposta combinando dados da atribuição e do suplemento.
    """
    return ClientSupplementRead(
        id=assignment.id,
        client_id=assignment.client_id,
        supplement_id=assignment.supplement_id,
        dose=assignment.dose,
        timing_notes=assignment.timing_notes,
        notes=assignment.notes,
        assigned_at=assignment.assigned_at,
        supplement_name=supplement.name,
        supplement_description=supplement.description,
        supplement_serving_size=supplement.serving_size,
        supplement_timing=supplement.timing,
        supplement_trainer_notes=supplement.trainer_notes,
    )

# ---------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------

@router.get("/clients/{client_id}/supplements", response_model=list[ClientSupplementRead])
async def list_client_supplements(
    client_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(require_active_subscription),
) -> list[ClientSupplementRead]:
    # Lista todos os suplementos atribuidos a um cliente especifico.

    try:
        # Verifica que o cliente existe e pertence ao trainer
        _get_client_or_404(client_id, current_user.id, session)

        # Busca as atribuições do cliente e os suplementos correspondentes
        assignments = session.exec(
            select(ClientSupplement).where(
                ClientSupplement.client_id == client_id,
                ClientSupplement.owner_trainer_id == current_user.id
            )
        ).all()

        results =[]
        for assignment in assignments:
            supplement = session.get(Supplement, assignment.supplement_id)
            if supplement:
                results.append(_build_response(assignment, supplement))

        return results
    except Exception as e:
        raise HTTPException(status_code=400, detail="Erro ao listar suplementos do cliente: ") from e
    
   

@router.post("/clients/{client_id}/supplements", response_model=ClientSupplementRead, status_code=status.HTTP_201_CREATED)
async def assign_supplement_to_client(
    client_id: str,
    payload: ClientSupplementAssign,
    session: Session = Depends(db_session),
    current_user = Depends(require_active_subscription),
) -> ClientSupplementRead:
    
    # Atribui um suplemento a um cliente, com dose e timing especificos.

    try:
        # Verifica que o cliente existe e pertence ao trainer
        _get_client_or_404(client_id, current_user.id, session)

        # Verifica que o suplemento existe e pertence ao trainer
        supplement = _get_supplement_or_404(payload.supplement_id, current_user.id, session)

        # Cria a atribuição
        assignment = ClientSupplement(
            client_id=client_id,
            supplement_id=payload.supplement_id,
            owner_trainer_id=current_user.id,
            dose=payload.dose,
            timing_notes=payload.timing_notes,
            notes=payload.notes,
        )
        session.add(assignment)
        commit_or_rollback(session)
        session.refresh(assignment)

        return _build_response(assignment, supplement)
    
    except Exception as e:
        raise HTTPException(status_code=400, detail="Erro ao atribuir suplemento ao cliente: ") from e
    
@router.patch("/clients/{client_id}/supplements/{assignment_id}", response_model=ClientSupplementRead)
async def update_supplement_assignment(
    client_id: str,
    assignment_id: str,
    payload: ClientSupplementUpdate,
    session: Session = Depends(db_session),
    current_user = Depends(require_active_subscription),
) -> ClientSupplementRead:
    
    # Actualiza a dose, timing ou notas de uma atribuicao de suplemento a cliente.

    try:

        _get_client_or_404(client_id, current_user.id, session)
        # Verifica que a atribuicao existe e pertence ao cliente e trainer
        assignment = _get_assignment_or_404(assignment_id, client_id, current_user.id, session)

        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(assignment, key, value)

        session.add(assignment)
        commit_or_rollback(session)
        session.refresh(assignment)

        # Busca o suplemento para construir a resposta
        supplement = session.get(Supplement, assignment.supplement_id)
        return _build_response(assignment, supplement)
    
    except Exception as e:
        raise HTTPException(status_code=400, detail="Erro ao actualizar atribuição de suplemento: ") from e
    
@router.delete("/clients/{client_id}/supplements/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_supplement_from_client(
    client_id: str,
    assignment_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(require_active_subscription),
):
    # Remove a atribuicao de um suplemento a um cliente (delete definitivo).

    try:
        _get_client_or_404(client_id, current_user.id, session)
        # Verifica que a atribuicao existe e pertence ao cliente e trainer
        assignment = _get_assignment_or_404(assignment_id, client_id, current_user.id, session)

        session.delete(assignment)
        commit_or_rollback(session)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Erro ao remover suplemento do cliente: ") from e