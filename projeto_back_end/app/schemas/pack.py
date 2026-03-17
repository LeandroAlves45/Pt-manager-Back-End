from typing import Optional
from datetime import date
from sqlmodel import SQLModel, Field

# =========================
# Client Pack (purchase)
# =========================

class ClientPackPurchase(SQLModel):
    """
        Compra de pack para um cliente:
        -escolhe o pack_type_id 
     """

    pack_type_id: str
    purchase_at: Optional[date] = None  #data da compra, se não for fornecida, usa a data atual


class ClientPackRead(SQLModel):
    """
    Schema para leitura de dados do pack do cliente.
    usado em respostas de API
    """

    id: str
    client_id: str
    client_name: Optional[str] = None
    pack_type_id: str
    purchase_at: date
    sessions_total_snapshot: int
    sessions_used: int
    cancelled_at: Optional[date] = None
    archived_at: Optional[date] = None
    created_at: date
    updated_at: date

