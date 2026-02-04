from typing import Optional
from datetime import date
from sqlmodel import SQLModel, Field

class PackTypeCreate(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    sessions_total: int = Field(ge=1, le=100)


class PackTypeRead(SQLModel):
    id: str
    name: str
    sessions_total: int
    is_active: bool
    created_at: date
    updated_at: date


#Schema para update de pack type
class PackTypeUpdate(SQLModel):
    name: Optional[str] = Field(default=None, min_length=1)           # Novo nome do pack (ex: "Pack 6 aulas")
    sessions_total: Optional[int] = Field(default=None, ge=1, le=500) # Total de sessões do pack (ex: 2,4,6,8)
    is_active: Optional[bool] = Field(default=None)                   # Ativar/desativar o pack