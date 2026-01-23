import uuid
from datetime import date
from typing import Optional

from sqlmodel import SQLModel, Field

class Client(SQLModel, table=True):
    """
    Representa um cliente/aluno na base de dados

    Nota:
    - UUID  é armazenado como string (SQLite) para simplicidade
    - birth_date é uma date; a idade é calculada na aplicação (não guardamos "age").
    - archived_at permite "soft delete" (arquivo), sem apagar histórico.
    """

    __tablename__ = "clients"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    full_name: str = Field(index=True, min_length=1)
    phone: str = Field(index=True, min_length=7, max_length=15)
    email: Optional[str] = Field(default=None, index=True)
    birth_date: date
    sex: Optional[str] = Field(default=None) #no futuro: Enum/check constraint via migração
    height_cm: Optional[int] = Field(default=None, ge=80, le=260) #altura em cm
    objetive: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None)

    emergency_contact_name: Optional[str] = Field(default=None)
    emergency_contact_phone: Optional[str] = Field(default=None)

    archived_at: Optional[date] = Field(default=None, index=True)

    created_at: str = Field(default_factory=lambda: _utc_now_iso())
    updated_at: str = Field(default_factory=lambda: _utc_now_iso())

def _utc_now_iso() -> str:
    """
    Gera timestamp ISO-8601 UTC como string.
    Mantemos string para compaqtibilidade SQLite e simplicidade.
    """
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()