from datetime import date
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class PortalBrandingRead(BaseModel):
    """
    DTO de saída específico do portal.
    Mantém o contrato de branding explícito sem expor diretamente o model ORM.
    """

    app_name: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    body_color: Optional[str] = None


class ClientPortalProfileRead(BaseModel):
    """
    Contrato de leitura do perfil do cliente autenticado no portal.
    Mantém o payload estável para o frontend sem expor diretamente o model ORM.
    """

    id: str
    full_name: str
    email: Optional[str] = None
    phone: str
    birth_date: Optional[date] = None
    sex: Optional[str] = None
    height_cm: Optional[int] = None
    training_modality: str
    objective: Optional[str] = None
    notes: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


class ClientPortalProfileUpdate(BaseModel):
    """
    Payload de atualização do perfil do cliente autenticado.
    O endpoint resolve sempre o cliente pelo JWT e ignora qualquer noção de client_id no body.
    """

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    phone: Optional[str] = Field(default=None, min_length=8, max_length=20)
    email: Optional[EmailStr] = None
    birth_date: Optional[date] = None
    sex: Optional[str] = None
    height_cm: Optional[int] = Field(default=None, ge=80, le=260)
    training_modality: Optional[str] = None
    notes: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("sex")
    @classmethod
    def normalize_sex(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
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
        if normalized not in mapping:
            raise ValueError("Sexo deve ser: male, female, other, unknown")
        return mapping[normalized]

    @field_validator("training_modality")
    @classmethod
    def validate_training_modality(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        allowed = {"presencial", "online"}
        if value not in allowed:
            raise ValueError(f"training_modality deve ser: {', '.join(sorted(allowed))}")
        return value
