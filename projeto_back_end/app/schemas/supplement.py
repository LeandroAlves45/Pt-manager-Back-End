from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field


class SupplementCreate(BaseModel):
    """
    Esquema para criar um suplemento.
    """
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    serving_size: Optional[str] = Field(default=None, max_length=50) #ex: "5g", "1 scoop", "2 cápsulas"
    timing: Optional[str] = Field(default=None, max_length=50) #ex: pré-treino, pós-treino, ao acordar, antes de dormir
    trainer_notes: Optional[str] = Field(default=None) #Notas internas para o trainer, não visíveis para clientes

class SupplementUpdate(BaseModel):
    """
    Esquema para atualizar um suplemento.
    Todos os campos são opcionais para permitir atualizações parciais.
    """
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    serving_size: Optional[str] = Field(default=None, max_length=50) #ex: "5g", "1 scoop", "2 cápsulas"
    timing: Optional[str] = Field(default=None, max_length=50) #ex: pré-treino, pós-treino, ao acordar, antes de dormir
    trainer_notes: Optional[str] = Field(default=None) #Notas internas para o trainer, não visíveis para clientes

class SupplementRead(BaseModel):
    """
    Esquema para leitura de um suplemento.
    Inclui campos de auditoria e FK para o trainer que criou o suplemento.
    """
    id: str
    name: str
    description: Optional[str]
    serving_size: Optional[str]
    timing: Optional[str]
    trainer_notes: Optional[str]
    archived_at: Optional[datetime]
    created_by_user_id: str
    archived_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

class SupplementReadPublic(BaseModel):
    """
    Esquema para leitura pública de um suplemento.
    Exclui campos internos e de auditoria, deixando apenas as informações relevantes para os clientes.
    """
    id: str
    name: str
    description: Optional[str]
    serving_size: Optional[str]
    timing: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }