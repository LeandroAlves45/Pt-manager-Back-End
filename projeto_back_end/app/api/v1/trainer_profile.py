"""
Router de perfil e branding do trainer.
 
Endpoints:
    GET   /trainer-profile/settings        — branding (cor, logo, app_name) — usado no login
    PATCH /trainer-profile/settings        — actualizar cor primária e app_name
    GET   /trainer-profile/profile         — perfil completo do trainer
    POST  /trainer-profile/logo            — upload de logo para Cloudinary
    DELETE /trainer-profile/logo           — remover logo
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlmodel import Session, select
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel

from app.api.deps import db_session
from app.db.models.user import User
from app.db.models.trainer_settings import TrainerSettings
from app.services.upload_service import UploadService
from app.core.config import settings
from app.core.security import require_active_subscription, require_trainer
from app.core.db_errors import commit_or_rollback
from app.utils.time import utc_now


router = APIRouter(prefix="/trainer-profile", tags=["Trainer Profile"])

#Tipos de imagem permitidos para upload de logo
ALLOWED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/jpg", "image/webp"]

# Tamanho máximo do logo (5MB)
MAX_LOGO_SIZE = 5 * 1024 * 1024

# =============================================================================
# Schema de settings (inline — simples o suficiente para não precisar ficheiro
# separado em schemas/)
# =============================================================================

class TrainerSettingsRead(BaseModel):
    """Resposta do GET /settings — usado pelo AuthContext para aplicar branding."""
    primary_color: Optional[str]
    body_color: Optional[str] = None
    app_name: Optional[str]
    logo_url: Optional[str]

class TrainerSettingsUpdate(BaseModel):
    """Cor primária, cor do fundo e nome da app são editáveis pelo Personal Trainer."""
    primary_color: Optional[str] = None
    body_color: Optional[str] = None
    app_name: Optional[str] = None

# =============================================================================
# Helper — obter ou criar TrainerSettings para o trainer autenticado
# =============================================================================

def get_or_create_trainer_settings(trainer_id: int, session: Session) -> TrainerSettings:
    """ Devolve as TrainerSettings para um trainer, ou cria se não existirem. """
    ts = session.exec(
        select(TrainerSettings).where(TrainerSettings.trainer_user_id == trainer_id)
    ).first()

    if not ts:
        ts = TrainerSettings(
            trainer_user_id=trainer_id,
            primary_color="#00AE8",
            app_name=None,
            logo_url=None,
        )
        session.add(ts)
        commit_or_rollback(session)
        session.refresh(ts)

    return ts

# =============================================================================
# GET /settings — branding do trainer (usado pelo AuthContext no login e restore)
# =============================================================================
@router.get("/settings", response_model=TrainerSettingsRead, status_code=status.HTTP_200_OK)
async def get_trainer_settings(
    current_user: User = Depends(require_trainer),
    session: Session = Depends(db_session),
) -> TrainerSettingsRead:
    """
    Devolve as configurações de branding do trainer autenticado.
    Usado pelo AuthContext em cada reload de página para aplicar a cor primária
    e o nome da app antes de renderizar o dashboard.
    """

    ts = get_or_create_trainer_settings(current_user.id, session)
    
    return TrainerSettingsRead(
        primary_color=ts.primary_color,
        body_color=getattr(ts, "body_color", None),  
        app_name=ts.app_name,
        logo_url=current_user.logo_url or current_user.logo_url,  # O logo é guardado no User, não nas TrainerSettings
    )

# =============================================================================
# PATCH /settings — actualizar cor primária e nome da app
# =============================================================================
@router.patch("/settings", response_model=TrainerSettingsRead, status_code=status.HTTP_200_OK)
async def update_trainer_settings(
    payload: TrainerSettingsUpdate,
    current_user: User = Depends(require_trainer),
    session: Session = Depends(db_session),
) -> TrainerSettingsRead:
    """
    Actualiza as configurações de branding do trainer.
    Apenas os campos enviados no payload são alterados (PATCH parcial).
    """

    ts = get_or_create_trainer_settings(current_user.id, session)

    if payload.primary_color is not None:
        color = payload.primary_color.strip()
        if not color.startswith("#") or len(color) not in (4, 7):
            raise HTTPException(status_code=400, detail="Cor primária deve ser um código hexadecimal válido (ex: #00AE8).")
        ts.primary_color = color

    if payload.app_name is not None:
        ts.app_name = payload.app_name.strip() or None  # Permitir limpar o nome da app com string vazia

    if payload.body_color is not None:
        color = payload.body_color.strip()
        if color and (not color.startswith("#") or len(color) not in (4, 7)):
            raise HTTPException(status_code=400, detail="Cor do fundo deve ser um código hexadecimal válido (ex: #0A0A14) ou null para usar o padrão.")
        ts.body_color = color or None  # Permitir limpar a cor do fundo com string
    elif 'body_color' in payload.model_fields_set:
        ts.body_color = None  # Se body_color for explicitamente enviado como null, limpar a cor do fundo

    ts.updated_at = utc_now()
    session.add(ts)
    commit_or_rollback(session)
    session.refresh(ts)

    return TrainerSettingsRead(
        primary_color=ts.primary_color,
        body_color=getattr(ts, "body_color", None),
        app_name=ts.app_name,
        logo_url=current_user.logo_url or current_user.logo_url,  # O logo é guardado no User, não nas TrainerSettings
    )

# =============================================================================
# POST /logo — upload de logo para Cloudinary
# =============================================================================

@router.post("/logo", status_code=status.HTTP_200_OK)
async def upload_trainer_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_active_subscription),
    session: Session = Depends(db_session),
):
    #Faz upload do logo do trainer

    try:
        # Validar se o utilizador é um trainer
        if current_user.role != "trainer":
            raise HTTPException(status_code=403, detail="Apenas trainers podem fazer upload de logo.")
        
        # Validar tipo de ficheiro
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Tipo de ficheiro não permitido. Apenas PNG, JPEG, JPG e WEBP são aceitos.")
        
        #Ler o conteudo do ficheiro
        file_bytes = await file.read()

        # Validar tamanho do ficheiro
        if len(file_bytes) > MAX_LOGO_SIZE:
            raise HTTPException(status_code=400, detail="Tamanho do ficheiro excede o limite de 5MB.")
        
        # Fazer upload para o Cloudinary
        logo_url = UploadService.upload_trainer_logo(
            file_bytes=file_bytes,
            trainer_id=current_user.id,
            content_type=file.content_type,
        )

        # Guardar URL do logo na BD
        current_user.logo_url = logo_url
        session.add(current_user)

        commit_or_rollback(session)
        session.refresh(current_user)
    
        return {"logo_url": logo_url, "message": "Logo atualizado com sucesso."}
    
    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao fazer upload do logo: {e}")


# =============================================================================
# DELETE /logo — remover logo
# =============================================================================

@router.delete("/logo", status_code=status.HTTP_200_OK)
async def delete_trainer_logo(
    current_user: User = Depends(require_active_subscription),
    session: Session = Depends(db_session),
):
    #Remove o logo do trainer

    try:
        # Validar se o utilizador é um trainer
        if current_user.role != "trainer":
            raise HTTPException(status_code=403, detail="Apenas trainers podem remover o logo.")
        
        if not current_user.logo_url:
            raise HTTPException(status_code=400, detail="Nenhum logo para remover.")
        
        # Remover do Cloudinary
        UploadService.delete_trainer_logo(current_user.id)
        
        # Remover URL do logo da BD
        current_user.logo_url = None
        session.add(current_user)
        commit_or_rollback(session)
        session.refresh(current_user)
    
        return {"message": "Logo removido com sucesso."}
    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover logo: {e}")

# =============================================================================
# GET /profile — perfil completo do trainer
# =============================================================================

@router.get("/profile", status_code=status.HTTP_200_OK)
async def get_trainer_profile(
    current_user: User = Depends(require_active_subscription),
    session: Session = Depends(db_session),
):
    #Retorna os dados do perfil do trainer

    if current_user.role != "trainer":
        raise HTTPException(status_code=403, detail="Apenas trainers podem acessar este endpoint.")
    
    ts = get_or_create_trainer_settings(current_user.id, session)
    
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "logo_url": current_user.logo_url,
        "role": current_user.role,
        "primary_color": ts.primary_color,
        "app_name": ts.app_name,
    }