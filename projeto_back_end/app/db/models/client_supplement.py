"""
Modelo da tabela de atribuicao de suplementos a clientes.
 
Representa a relacao muitos-para-muitos entre Client e Supplement,
enriquecida com campos especificos por atribuicao:
    - dose: pode ser diferente da dose padrao do suplemento
    - timing_notes: pode sobrepor o timing padrao
    - notes: instrucoes especificas do trainer para este cliente
 
Multi-tenancy:
    owner_trainer_id e armazenado directamente no registo para que
    as queries de listagem por trainer nao precisem de JOIN com clients.
"""

import uuid
from typing import Optional
from datetime import datetime

from sqlmodel import Field, SQLModel
from app.utils.time import utc_now_datetime

class ClientSupplement(SQLModel, table=True):
    """
    Registo de atribuicao de um suplemento a um cliente.
    """

    __tablename__="client_supplements"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    # FK para cliente que recebe o suplemento
    client_id: str = Field(foreign_key="clients.id", index=True)

    # FK para suplemento atribuido
    supplement_id: str = Field(foreign_key="supplements.id", index=True)

    owner_trainer_id: str = Field(foreign_key="users.id", index=True)

    dose: Optional[str] = Field(default=None, max_length=100) #ex: "5g", "1 scoop", "2 cápsulas"
    timing_notes: Optional[str] = Field(default=None, max_length=200) #ex: "30 min antes do treino", "após o treino"
    notes: Optional[str] = Field(default=None, max_length=300)

    # Timestamp de quandp a atribuida foi criada
    assigned_at: datetime = Field(default_factory=utc_now_datetime)