from __future__ import annotations
from datetime import date
from typing import Optional
from sqlmodel import Session, select

from app.db.models.pack import PackType, ClientPack
from app.db.models.client import Client
from app.core.db_errors import commit_or_rollback
from app.utils.time import utc_now

class PackService:
    """
    Serviços de negócio relacionados a pacotes.

    Aqui é onde fica:
    -compra do pack (com snapchot sessions_total do pack_type)
    - querys "pack ativo"
    """

    @staticmethod
    def now_iso() -> date:
        """Data UTC atual."""
        return utc_now()
    

    @staticmethod
    def purchase_pack(
        session: Session,
        client_id: str,
        pack_type_id: str,
        purchase_at: Optional[date] = None,
    ) -> ClientPack:
        """
        Compra um pack:
        Valida se o pack_type existe e o cliente existe.
        -Copia sessions_total do pack type para o client_pack (snapshot)
        """

        client = session.get(Client, client_id)
        if not client:
            raise ValueError("Cliente não encontrado.")
        
        if client.archived_at is not None:
            raise ValueError("Não é possível comprar um pack para um cliente arquivado.")
        
        pack_type = session.get(PackType, pack_type_id)
        if not pack_type:
            raise ValueError("Tipo de pack não encontrado.")
        
         #definir timestamps
        purchased_at = purchase_at or PackService.now_iso()
        
        client_pack = ClientPack(
            client_id=client_id,
            pack_type_id=pack_type_id,
            client_name = client.full_name,
            purchase_at=purchased_at,
            sessions_total=pack_type.sessions_total,
            sessions_used=0,
        )

        session.add(client_pack)
        commit_or_rollback(session)
        session.refresh(client_pack)
        return client_pack  
    
    @staticmethod
    def get_active_pack(session: Session, client_id: str) -> ClientPack:
        """
        Retorna os packs ativos de um cliente.
        Pack ativo é aquele que não está cancelado e tem sessões restantes.
        """

        statement = (select(ClientPack)
        .where(ClientPack.client_id == client_id)
        .where(ClientPack.archived_at.is_(None))
        .where(ClientPack.cancelled_at.is_(None))
        .where(ClientPack.sessions_used < ClientPack.sessions_total_snapshot)
        .order_by(ClientPack.purchase_at.desc())
        ).limit(1)
        
        return session.exec(statement).first()
        


