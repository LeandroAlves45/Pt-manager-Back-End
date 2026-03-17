from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.utils.time import utc_now
from app.api.deps import db_session
from app.db.models.client import Client
from app.db.models.pack import PackType, ClientPack
from app.schemas.pack import ClientPackPurchase, ClientPackRead
from app.services.pack_service import PackService
from app.core.db_errors import commit_or_rollback

router = APIRouter(prefix="/packs", tags=["Packs"])

@router.post("/clients/{client_id}/purchase", response_model=ClientPackRead, status_code=status.HTTP_201_CREATED)
async def purchase_pack_for_client(
    client_id: str,
    payload: ClientPackPurchase,
    session: Session = Depends(db_session),
) -> ClientPack:
    
    """
    Compra um pack para um cliente, com snapshot de sessions_total do pack_type.
    """

    try:
        #garantir que o cliente existe
        client = session.get(Client, client_id)
        if not client:
            raise ValueError(f"Cliente com ID {client_id} não encontrado.")
        
        #Regra: não comprar pack para cliente arquivado
        if getattr(client, "archived_at", None) is not None:
            raise HTTPException(status_code=400, detail="Cliente arquivado não pode comprar packs.")
        
        #garantir que o pack existe
        pack_type = session.get(PackType, payload.pack_type_id)
        if not pack_type:
            raise ValueError(f"Tipo de pack não encontrado.")

        #Regra. impedir compra de pack se houver pack ativo do mesmo tipo
        active = PackService.get_active_pack(session=session, client_id=client_id)
        if active:
            raise ValueError("Cliente já possui um pack ativo. Não é permitido comprar um novo pack antes de finalizar o atual.")
        
        new_pack = ClientPack(
            client_id=client_id,
            pack_type_id=payload.pack_type_id,
            client_name=client.full_name,
            purchase_at=utc_now(),
            sessions_total_snapshot=pack_type.sessions_total,
            sessions_used=0,
        )

        session.add(new_pack)
        session.commit()
        session.refresh(new_pack)
        return new_pack
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=f"IntegrityError: {getattr(e, 'orig', e)}") from e
    except SQLAlchemyError as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"SQLAlchemyError: {getattr(e, 'orig', e)}") from e
    
@router.get("/clients/{client_id}", response_model=list[ClientPackRead])
async def list_client_packs(client_id: str, session: Session = Depends(db_session)) -> list[ClientPack]:
    """
    Lista packs comprados por um cliente.
    """
    try:
        stmt = (
            select(ClientPack)
            .where(ClientPack.client_id == client_id)
            .order_by(ClientPack.purchase_at.desc())
        )
        return list(session.exec(stmt).all())
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao listar packs do cliente.") from e


@router.get("/clients/{client_id}/active", response_model=ClientPackRead | None)
async def get_active_pack(client_id: str, session: Session = Depends(db_session)) -> ClientPack | None:
    """
    Retorna o pack ativo (se existir).
    """
    try:
        return PackService.get_active_pack(session=session, client_id=client_id)
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao obter pack ativo.") from e