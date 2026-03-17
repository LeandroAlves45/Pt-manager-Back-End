"""
Serviço de upload de imagens para o Cloudinary.

Uso do Cloudinary:
  - Armazenamento externo (Railway não tem disco persistente)
  - URL pública gerada automaticamente (necessário para emails via Resend)
  - Transformações de imagem gratuitas (resize, crop, optimize)
  - Plano gratuito: 25GB armazenamento + 25GB bandwidth/mês
"""

import cloudinary
import cloudinary.uploader
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class UploadService:

    @staticmethod
    def configure():
        """
        Configura o cliente Cloudinary usando as credenciais do .env
        """
        if not all([settings.cloudinary_cloud_name, settings.cloudinary_api_key, settings.cloudinary_api_secret]):
            raise ValueError("Cloudinary credentials não configuradas. Defina CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY e CLOUDINARY_API_SECRET no .env")
        
        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True,
        )

    @staticmethod
    def upload_trainer_logo(
        file_bytes: bytes,
        trainer_id: str,
        content_type: str = "image/png",
    ) -> str:
        """
        Faz upload do logo do trainer para o Cloudinary.

        O logo é guardado numa pasta organizada por trainer_id,
        o que facilita a gestão e garante isolamento entre trainers.

        Args:
            file_bytes:   Conteúdo do ficheiro em bytes
            trainer_id:   ID do trainer (usado como nome do ficheiro)
            content_type: Tipo MIME da imagem (image/png, image/jpeg, etc.)

        Returns:
            str: URL pública permanente da imagem no Cloudinary

        Raises:
            ValueError: Se o upload falhar
        """

        UploadService.configure()

        try:
            # public_id define o caminho e nome no Cloudinary
            # Exemplo resultado: "pt_manager/logos/trainer_abc123"
            # Se o trainer fizer novo upload, substitui o anterior (overwrite=True)
            result = cloudinary.uploader.upload(
                file_bytes,
                public_id=f"pt_manager/logos/trainer_{trainer_id}",
                overwrite=True,
                resource_type="image",
                format="png",  # força conversão para PNG 
                transformation=[
                    {
                        "width": 400,
                        "height": 200,
                        "crop": "fit",
                        "quality": "auto",
                    }
                ],
            )

            url: str = result.get("secure_url")
            logger.info(f"[UPLOAD] ✅ Logo do trainer {trainer_id} carregado com sucesso: {url}")
            return url
        
        except Exception as e:
            logger.error(f"[UPLOAD] ❌ Erro ao carregar logo do trainer {trainer_id}: {e}")
            raise ValueError(f"Erro ao carregar logo do trainer: {e}")
    
    @staticmethod
    def delete_trainer_logo(trainer_id: str) -> None:
        """
        Remove a logo do personal trainer do Cloudinary.
        Chamado quando o personal trainer é eliminado ou substitui o logo.
        """

        UploadService.configure()

        try:
            cloudinary.uploader.destroy(f"pt_manager/logos/trainer_{trainer_id}")
            logger.info(f"[UPLOAD] Logo do Personal Trainer {trainer_id} eliminado do Cloudinary.")
        
        except Exception as e:
            logger.error(f"[UPLOAD] ❌ Erro ao eliminar logo do Personal Trainer {trainer_id}: {e}")