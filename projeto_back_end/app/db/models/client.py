import uuid
from datetime import date
from typing import Optional

from sqlmodel import SQLModel, Field
from app.utils.time import utc_now

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
    training_modality: str = Field(default="presencial", max_length=20) #presencial, online ou híbrido
    next_assessment_date: Optional[date] = Field(default=None) #data da próxima avaliação física

    owner_trainer_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)

    emergency_contact_name: Optional[str] = Field(default=None)
    emergency_contact_phone: Optional[str] = Field(default=None)

    archived_at: Optional[date] = Field(default=None, index=True)

    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)