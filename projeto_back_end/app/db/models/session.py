"""
Modelos de base de dados para sessões de treino e consumo de packs.
 
TrainingSession — regista uma sessão individual agendada entre trainer e cliente.
PackConsumption — regista o consumo de uma sessão num pack do cliente.
"""

import uuid
from typing import Optional
from datetime import datetime

from sqlmodel import Field, SQLModel
from app.utils.time import utc_now

class TrainingSession (SQLModel, table = True):
    """
    Representa uma sessão de treino individual (presencial ou híbrida).
 
    Estados do ciclo de vida (campo status):
        scheduled  — agendada, ainda não ocorreu
        completed  — concluída, deduz uma sessão do pack activo
        cancelled  — cancelada pelo trainer ou cliente
        no-show    — cliente não compareceu
 
    Multi-tenancy:
        owner_trainer_id é obrigatório e garante que um trainer nunca
        consegue aceder a sessões de outro trainer, mesmo conhecendo o ID.
    """

    __tablename__ = "sessions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    # FK para o cliente a quem pertence esta sessão.
    client_id: str = Field(index = True, foreign_key="clients.id")

    # Desnormalizado: evita joins na listagem de sessões
    client_name: Optional[str] = Field(default=None)

    # O trainer é o "owner" da sessão, garante isolamento total entre trainers
    owner_trainer_id: Optional[str] = Field(default=None,index=True, foreign_key="users.id")

    starts_at: datetime = Field(index =True)
    duration_minutes: int = Field(ge=15, le=240)

    location: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None)

    status: str = Field(default="scheduled", index=True, max_length=20)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

class PackConsumption(SQLModel, table=True):
    """
    Registo de consumo de uma sessão num pack do cliente.
 
    Criado automaticamente quando uma sessão é marcada como "completed".
    Liga a sessão concluída ao pack que foi decrementado.
 
    Relação:
        Uma sessão completed → cria um PackConsumption → decrementa ClientPack.sessions_used
    """

    __tablename__ = "pack_consumptions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    session_id: str = Field(index=True, foreign_key="sessions.id")

    client_pack_id: str = Field(index=True, foreign_key="client_packs.id")
    
    created_at: datetime = Field(default_factory=utc_now)


