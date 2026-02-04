import uuid
from typing import Optional
from datetime import date

from sqlmodel import Field, SQLModel
from app.utils.time import utc_now

class TrainingSession (SQLModel, table = True):
    """
    Aulas / sessões de treino individuais.

    Status:
    - scheduled: agendada
    - completed: concluída
    - canceled: cancelada
    -no-show: não compareceu
    """

    __tablename__ = "sessions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    client_id: str = Field(index = True, foreign_key="clients.id")
    client_name: Optional[str] = Field(default=None)

    starts_at: date = Field(index =True)
    duration_minutes: int = Field(ge=15, le=240)

    location: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None)

    status: str = Field(default="scheduled", index=True, max_length=20)
    created_at: date = Field(default_factory=utc_now)
    updated_at: date = Field(default_factory=utc_now)

class PackConsumption(SQLModel, table=True):
    """
    Registo de consumo de packs por sessões de treino.
    """

    __tablename__ = "pack_consumptions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)
    session_id: str = Field(index=True, foreign_key="sessions.id")
    client_pack_id: str = Field(index=True, foreign_key="client_packs.id")

    created_at: date = Field(default_factory=utc_now)