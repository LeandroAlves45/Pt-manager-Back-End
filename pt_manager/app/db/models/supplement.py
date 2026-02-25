import uuid
from typing import Optional
from datetime import datetime

from sqlmodel import Field, SQLModel
from app.utils.time import utc_now

class Supplement(SQLModel, table=True):
    """
    Representa um suplemento no catálogo da plataforma.

    Criado e gerido exclusivamente por trainers.
    Pode ser consultado por clientes (read-only).

    Exemplos: Creatina, BCAA, Vitamina D, Omega-3, etc.
    """

    __tablename__ = "supplements"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    name: str = Field(index=True, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)

    #Informações nutricionais por dose (ex: por scoop, por cápsula)
    serving_size: Optional[str] = Field(default=None, max_length=50) #ex: "5g", "1 scoop", "2 cápsulas"
    
    #Altura em que tomar o suplemento (ex: pré-treino, pós-treino, ao acordar, antes de dormir)
    timing: Optional[str] = Field(default=None, max_length=50)

    trainer_notes: Optional[str] = Field(default=None) #Notas internas para o trainer, não visíveis para clientes

    archived_at: Optional[datetime] = Field(default=None) #Data de arquivamento para permitir soft delete e histórico

    created_by_user_id: str = Field(foreign_key="users.id", index=True) #FK para o trainer que criou o suplemento

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)