from typing import Optional
from pydantic import Field
from sqlmodel import SQLModel
from datetime import date

class TrainingSessionCreate(SQLModel):
    """
    Agendar uma sessão de treino individual.
    """

    starts_at: date
    duration_minutes: int = Field(ge=15, le=240)
    location: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None)

class TrainingSessionRead(SQLModel):
    id: str
    client_id: str
    client_name: Optional[str]
    starts_at: date
    duration_minutes: int
    location: Optional[str]
    notes: Optional[str]
    status: str
    created_at: date    
    updated_at: date

class TrainingSessionUpdate(SQLModel):
    """
    Atualização parcial de uma sessão de treino.
    """

    starts_at: Optional[date] = None
    duration_minutes: Optional[int] = Field(default=None, ge=15, le=240)
    location: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = None
    status: Optional[str] = Field(default=None, max_length=20)  # scheduled | completed | canceled | no-show