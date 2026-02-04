from datetime import date
from typing import Optional

from pydantic import EmailStr, field_validator, BaseModel
from sqlmodel import SQLModel, Field
from sqlalchemy.exc import IntegrityError

class ClientCreate(SQLModel):
    """
    Payload para criação de um novo cliente.
    aqui validamos formato; regras de negócio mais avançadas ficam em services
    """

    full_name: str = Field(min_length = 1, max_length=200)
    phone: str = Field(min_length = 8, max_length=20)
    email: Optional[EmailStr] = None

    birth_date: date
    @field_validator('sex')
    @classmethod
    def normalize_sex(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        mapping = {
            "male": "male",
            "m": "male",
            "masculino": "male",
            "female": "female",
            "f": "female",
            "feminino": "female",
            "other": "other",
            "unknown": "unknown",
        }
        if v not in mapping:
            raise ValueError("Sexo deve ser: male, female, other, unknown")
        return mapping[v]
    sex: Optional[str] = Field(default = None)

    height_cm: Optional[int] = Field(default=None, ge= 80, le= 260)
    objetive: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = None

    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

class ClientUpdate(SQLModel):
    """
    Payload para atualização de um cliente.
    todos os campos são opcionais
    """

    full_name: Optional[str] = Field(default=None, min_length = 1, max_length=200)
    phone: Optional[str] = Field(default=None, min_length = 8, max_length=20)
    email: Optional[EmailStr] = None

    birth_date: Optional[date] = None
    sex: Optional[str] = None

    height_cm: Optional[int] = Field(default=None, ge= 80, le= 260)
    objetive: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = None

    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

class ClientRead(SQLModel):
    """
    Schema para leitura de dados do cliente.
    usado em respostas de API
    """

    id: str
    full_name: str
    phone: str
    email: Optional[str]

    birth_date: date
    sex: Optional[str] 
    height_cm: Optional[int]
    objetive: Optional[str] = None
    notes: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    status: str #ativo ou arquivado
    created_at: date
    updated_at: date

class ActivePackInfo(BaseModel):
    client_pack_id: str
    pack_type_id: str
    pack_type_name: str
    sessions_total: int
    sessions_used: int
    sessions_remaining: int

class ClientReadWithPack(ClientRead):
    active_pack: Optional[ActivePackInfo] = None
