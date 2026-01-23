import uuid
from typing import Optional

from sqlmodel import SQLModel, Field

class PackType(SQLModel, table=True):
    """
    Catalogo de tipos de packs de aulas (ex: "Pack 10 aulas", "Pack 20 aulas").

    sessions_total: número total de sessões incluídas no pack.
    """

    __tablename__ = "pack_types"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(index=True, min_length=1)
    sessions_total: int = Field(ge=1, le=500)
    created_at: str = Field(default_factory=lambda: _utc_now_iso())
    updated_at: str = Field(default_factory=lambda: _utc_now_iso())

class ClientPack(SQLModel, table=True):
    """
    Pack comprado por um cliente.(instância)

    sessions_total:
    -snapchot do número total de sessões no pack_type na compra
    -evita problemas se o pack_type for alterado depois da compra

    sessions_used:
    -contador consumido transacionalmente ao completar sessões

    auto_renew + next_pack_type_id + renewal_status:
    -só importam quando o pack termina
    -renewal_status: pending | renewed | cancelled
    """

    __tablename__ = "client_packs"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    client_id: str = Field(foreign_key="clients.id")
    pack_type_id: str = Field(foreign_key="pack_types.id")
    purchase_date: str = Field(default_factory=lambda: _utc_now_iso(), index=True)
    valid_until: Optional[str] = Field(default=None, index=True)

    sessions_total: int = Field(ge=1, le=500)
    sessions_used: int = Field(default=0, ge=0)

    auto_renew: bool = Field(default=False)
    next_pack_type_id: Optional[str] = Field(default=None, foreign_key="pack_types.id")
    renewal_status: str = Field(default="pending", index=True) #pending | renewed

    cancelled_at: Optional[str] = Field(default=None, index=True)
    arquived_at: Optional[str] = Field(default=None, index=True)

    created_at: str = Field(default_factory=lambda: _utc_now_iso())
    updated_at: str = Field(default_factory=lambda: _utc_now_iso())

def _utc_now_iso() -> str:
    """
    Gera timestamp ISO-8601 UTC como string.
    Mantemos string para compaqtibilidade SQLite e simplicidade.
    """
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()