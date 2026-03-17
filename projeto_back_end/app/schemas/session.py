from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class SessionSchedulePayload(BaseModel):
    """
    Schema para agendar uma nova sessão a partir de um pack.
    Recebe datetime completo (data + hora) para o início da sessão.
    """
    starts_at: datetime  # Alterado de date para datetime
    duration_minutes: int = Field(gt=0, description="Duração da sessão em minutos")
    location: str = Field(min_length=1, description="Local onde a sessão vai decorrer")
    notes: Optional[str] = Field(None, description="Notas adicionais sobre a sessão")
    