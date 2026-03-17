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
from sqlmodel import Session
from datetime import datetime, timezone
from typing import Optional

from app.api.deps import db_session
from app.db.models.user import User
from app.services.upload_service import UploadService
from app.core.config import settings
from app.core.security import require_active_subscription

router = APIRouter(prefix="/trainer-profile", tags=["Trainer Profile"])

#Tipos de imagem permitidos para upload de logo
ALLOWED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/jpg", "image/webp"]

# Tamanho máximo do logo (5MB)
MAX_LOGO_SIZE = 5 * 1024 * 1024

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
        session.commit()
        session.refresh(current_user)
    
        return {"logo_url": logo_url, "message": "Logo atualizado com sucesso."}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao fazer upload do logo: {e}")

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
        session.commit()
        session.refresh(current_user)
    
        return {"message": "Logo removido com sucesso."}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover logo: {e}")



@router.get("/profile", status_code=status.HTTP_200_OK)
async def get_trainer_profile(
    current_user: User = Depends(require_active_subscription),
):
    #Retorna os dados do perfil do trainer

    if current_user.role != "trainer":
        raise HTTPException(status_code=403, detail="Apenas trainers podem acessar este endpoint.")
    
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "logo_url": current_user.logo_url,
        "role": current_user.role,
    }