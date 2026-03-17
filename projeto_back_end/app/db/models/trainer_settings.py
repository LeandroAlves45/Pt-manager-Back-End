"""
Modelo ORM para as configurações de branding do trainer.
 
Cada trainer tem exactamente uma linha nesta tabela (relação 1:1 com users).
A tabela foi criada pela migration 004.
 
Campos de branding:
    primary_color  — cor hex do tema da app (ex: "#1A7A4A")
    logo_url       — URL do logo no Cloudinary (duplicado de users.logo_url por performance)
    logo_public_id — public_id do Cloudinary, necessário para eliminar o ficheiro no futuro
    app_name       — nome personalizado da app que aparece na sidebar e no título do browser
"""

import uuid
from typing import Optional
from datetime import datetime

from sqlmodel import SQLModel, Field
from app.utils.time import utc_now

class TrainerSettings(SQLModel, table=True):
    """
    Configurações de branding e preferências por trainer.
    Relação 1:1 com a tabela users (trainer_user_id é UNIQUE).
    """

    __tablename__ = "trainer_settings"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    # FK para o trainer - UNIQUE para garantir relação 1:1
    trainer_user_id: str = Field(foreign_key="users.id", unique=True, index=True)

    # Cor primária do tema em formato hex (com #)
    # Default: azul PT Manager. Injectada como CSS variable no login.
    primary_color: str = Field(default="#00A8E8", max_length=7)

    logo_url: Optional[str] = Field(default=None, max_length=500)

    # public_id do Cloudinary — necessário para chamar cloudinary.uploader.destroy()
    logo_public_id: Optional[str] = Field(default=None, max_length=500)

    app_name: Optional[str] = Field(default=None, max_length=100)

    # Timezone do trainer
    timezone: str = Field(default="Europe/Lisbon", max_length=50)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
