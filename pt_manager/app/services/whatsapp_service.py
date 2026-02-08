# app/services/whatsapp_service.py
from __future__ import annotations

import requests
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class WhatsAppService:
    """
    Serviço para envio de mensagens via WhatsApp Cloud API (Meta).
    
    Documentação: https://developers.facebook.com/docs/whatsapp/cloud-api
    
    Requisitos:
    1. Conta no Meta Business Manager
    2. App configurado com WhatsApp
    3. Token de acesso permanente
    4. Número de telefone verificado
    """
    
    @staticmethod
    def send_message(to_phone: str, body: str) -> None:
        """
        Envia mensagem de texto via WhatsApp Cloud API.
        
        Args:
            to_phone: Número no formato internacional (ex: "351912345678")
            body: Texto da mensagem (máx 4096 caracteres)
            
        Raises:
            ValueError: Se configuração estiver incompleta ou número inválido
            requests.HTTPError: Se API retornar erro
        """
        
        # Validar configuração
        if not settings.wa_phone_number_id or not settings.wa_token:
            error_msg = "WhatsApp não configurado. Defina WA_PHONE_NUMBER_ID e WA_TOKEN no .env"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Validar número (deve ser só dígitos após limpeza)
        clean_phone = to_phone.strip().replace("+", "").replace(" ", "").replace("-", "")
        if not clean_phone.isdigit() or len(clean_phone) < 10:
            raise ValueError(f"Número de telefone inválido: {to_phone}")
        
        # Construir request para WhatsApp Cloud API
        url = f"https://graph.facebook.com/v19.0/{settings.wa_phone_number_id}/messages"
        
        headers = {
            "Authorization": f"Bearer {settings.wa_token}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "to": clean_phone,  # Número sem caracteres especiais
            "type": "text",
            "text": {
                "body": body[:4096]  # WhatsApp limita a 4096 chars
            },
        }
        
        try:
            logger.info(f"Enviando WhatsApp para {clean_phone}")
            response = requests.post(url, headers=headers, json=payload, timeout=20)
            response.raise_for_status()
            logger.info(f"WhatsApp enviado com sucesso para {clean_phone}")
            
        except requests.exceptions.Timeout:
            logger.error("Timeout ao enviar WhatsApp")
            raise ValueError("Timeout ao conectar com WhatsApp API")
            
        except requests.exceptions.HTTPError as e:
            # Log do erro detalhado da API
            error_detail = response.json() if response.content else "Sem detalhes"
            logger.error(f"Erro HTTP {response.status_code} ao enviar WhatsApp: {error_detail}")
            raise ValueError(f"Erro ao enviar WhatsApp: {e}")
            
        except Exception as e:
            logger.exception("Erro inesperado ao enviar WhatsApp")
            raise ValueError(f"Erro inesperado: {e}")