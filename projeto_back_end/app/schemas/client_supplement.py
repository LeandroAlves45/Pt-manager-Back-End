"""
Schemas Pydantic para atribuicao de suplementos a clientes (SU-04/05).
 
ClientSupplementAssign  — payload para atribuir um suplemento a um cliente
ClientSupplementUpdate  — payload para actualizar dose/timing/notas (PATCH parcial)
ClientSupplementRead    — resposta com dados do suplemento expandidos (para o trainer)
ClientSupplementPublic  — resposta para o cliente (sem trainer_notes do suplemento)
"""

from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field

class ClientSupplementAssign(BaseModel):
    """
    Payload para atribuir um suplemento a um cliente.
    dose e timing_notes sao opcionais — se omitidos, o cliente ve os valores
    padrao do suplemento (serving_size e timing do catalogo).
    """
    supplement_id: str = Field(..., description="ID do suplemento do catálogo")
    dose: Optional[str] = Field(default=None, max_length=100, description="Dose específica para o cliente (ex: '5g', '1 scoop', '2 cápsulas').")
    timing_notes: Optional[str] = Field(default=None, max_length=200, description="Ex: '30 min antes do treino', 'após o treino'.")
    notes: Optional[str] = Field(default=None, max_length=300, description="Instruções específicas do Personal Trainer para este cliente.")

class ClientSupplementUpdate(BaseModel):
    """
    Payload para actualizar dose/timing/notas de um suplemento atribuido a um cliente.
    Todos os campos são opcionais e apenas os fornecidos serão actualizados.
    """
    dose: Optional[str] = Field(default=None, max_length=100)
    timing_notes: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None)

class ClientSupplementRead(BaseModel):
    """
    Resposta com dados do suplemento atribuido a um cliente, incluindo detalhes do suplemento do catálogo.
    Este schema é usado para o Personal Trainer, e inclui as notas específicas do cliente.
    """
    id: str
    supplement_id: str
    supplement_id: str
    dose: Optional[str]
    timing_notes: Optional[str]
    notes: Optional[str]
    assigned_at: datetime

    supplement_name: str
    supplement_description: Optional[str]
    supplement_serving_size: Optional[str]
    supplement_timing: Optional[str]
    supplement_trainer_notes: Optional[str] # Visível para o Personal Trainer

    model_config = {"from_attributes": True}

class ClientSupplementPublic(BaseModel):
    """
    Resposta para o cliente, com dados do suplemento atribuido, mas sem as notas específicas do Personal Trainer.
    Este schema é usado para o cliente, e omite as notas do treinador para evitar confusão.
    """
    id: str
    supplement_id: str
    dose: Optional[str]
    timing_notes: Optional[str]
    notes: Optional[str]
    assigned_at: datetime

    supplement_name: str
    supplement_description: Optional[str]
    supplement_serving_size: Optional[str]
    supplement_timing: Optional[str]

    model_config = {"from_attributes": True}