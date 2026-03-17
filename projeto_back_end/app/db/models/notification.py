import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import SQLModel, Field


class NotificationChannel(str, Enum):
    """Canais suportados para envio."""
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class RecipientType(str, Enum):
    """Tipo de destinatário."""
    CLIENT = "client"
    TRAINER = "trainer"


class NotificationStatus(str, Enum):
    """Estados do ciclo de vida da notificação."""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Notification(SQLModel, table=True):
    """
    Notificação agendada (não é só log).

    scheduled_for: quando deve disparar (UTC, timezone-aware no código)
    status:
      - pending
      - sent
      - failed
      - cancelled
    """

    __tablename__ = "notifications"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    session_id: str = Field(foreign_key="sessions.id", index=True)

    #usar Enum 
    channel: NotificationChannel = Field(index=True)
    recipient_type: RecipientType = Field(index=True)
    status: NotificationStatus = Field(default=NotificationStatus.PENDING, index=True)

    recipient: str = Field(max_length=200)
    message: str = Field(max_length=2000)

    scheduled_for: datetime = Field(index=True)

    sent_at: Optional[datetime] = Field(default=None)

    #Optional precisa de default=None para não ser "required" no schema
    error_message: Optional[str] = Field(default=None, max_length=1000)
