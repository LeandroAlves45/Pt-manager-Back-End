"""
Serviço de email via Resend API.
"""

from __future__ import annotations
from typing import Optional
import resend
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

class EmailService:
    """
        Serviço para envio de emails via Resend API.
    """

    @staticmethod
    def _configure():
        """
        Configura o cliente Resend usando a chave da API do .env
        """
        if not settings.resend_api_key:
            raise ValueError("Resend API key não configurada. Defina RESEND_API_KEY no .env")
        
        resend.api_key = settings.resend_api_key

    @staticmethod
    def load_email_template() -> str:
        """
        Carrega o template HTML do email.
        """
        template_path = Path("app/htmls/email.html")

        if not template_path.exists():
            error_msg = f"Template de email não encontrado em {template_path}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()
            return template
        except Exception as e:
            logger.error(f"Erro ao carregar template de email: {e}")
            raise ValueError(f"Erro ao carregar template de email: {e}")

    @staticmethod
    def get_email_template(
        client_name:str,
        session_date:str,
        session_time:str,
        duration_minutes:int,
        location:str,
        trainer_logo_url: str = ""
    ) -> str:
        """
        Carrega o template HTML e substitui as variáveis com os dados da sessão.

        As variáveis no HTML são: {client_name}, {session_date},
        {session_time}, {duration_minutes}, {location}, {trainer_logo_url}

        Returns:
            str: HTML completo com os dados substituídos
        """
        
        try:

            template_path = EmailService.load_email_template()

             # Substituir variáveis usando .format()
            html = template_path.format(
            client_name=client_name,
            session_date=session_date,
            session_time=session_time,
            duration_minutes=duration_minutes,
            location=location,
            trainer_logo_url=trainer_logo_url
            )
        
            logger.debug(f"[EMAIL] Template processado para {client_name}")
            return html
        
        except KeyError as e:
            error_msg = f"Variável {e} não encontrada no template HTML"
            logger.error(f"[EMAIL] ❌ {error_msg}")
            raise ValueError(error_msg)
        
        except Exception as e:
            logger.error(f"Erro ao carregar template de email: {e}")
            raise ValueError(f"Erro ao carregar template de email: {e}")
        
    @staticmethod
    def send_session_email(
        *,
        to_email: str,
        client_name:str,
        session_date:str,
        session_time:str,
        duration_minutes:int,
        location:str,
        trainer_logo_url: str = ""
    ) -> None:
        """
        Envia email de lembrete de sessão presencial ao cliente via Resend.

        Usa o template HTML com as variáveis substituídas.
        O logo no HTML usa 'cid:logo' — com Resend não funciona como
        attachment inline, por isso o logo deve estar hospedado numa URL
        pública e o HTML deve usar <img src="https://..."> em vez de cid:logo.

        Args:
            to_email:           Email do destinatário
            client_name:        Nome do cliente
            session_date:       Data formatada (ex: "15/03/2026")
            session_time:       Hora formatada (ex: "10:00")
            duration_minutes:   Duração em minutos
            location:           Local do treino
            trainer_logo_url:   URL do logo do treinador (opcional)
        """
        EmailService._configure()

        html_body = EmailService.get_email_template(
            client_name=client_name,
            session_date=session_date,
            session_time=session_time,
            duration_minutes=duration_minutes,
            location=location,
            trainer_logo_url=trainer_logo_url
        )
        #testo simples de fallback (para clientes de email sem suporte a HTML)
        text_body=(
            f"Olá {client_name}, \n\n"
            f"Tens um treino agendado para amanhâ:\n"
            f"Data: {session_date}\n"
            f"Hora: {session_time}\n"
            f"Duração: {duration_minutes} minutos\n"
            f"Local: {location}\n\n"
            "Até lá!"
        )

        try:
            resend.Email.create({
                "from": settings.email_from,
                "to": [to_email],
                "subject": f"Lembrete de treino - {session_date} às {session_time}",
                "html": html_body,
                "text": text_body
            })
            logger.info(f"[EMAIL] ✅ Email enviado para {to_email}")

        except Exception as e:
            logger.error(f"[EMAIL] ❌ Erro ao enviar email para {to_email}: {e}")
            raise ValueError(f"Erro ao enviar email: {e}")
        
    @staticmethod
    def send_trainer_reminder(
        *,
        trainer_email: str,
        client_name:str,
        session_date:str,
        session_time:str,
        duration_minutes:int,
        location:str,
        notes: Optional[str] = None
    ) -> None:
        """
        Envia lembrete simples (texto) ao trainer sobre a sessão do dia seguinte.
        Não usa template HTML — é um email interno, não precisa de design.
        """
        EmailService._configure()

        body = (
            f"Lembrete de Treino para amanhã:\n\n"
            f"Cliente: {client_name}\n"
            f"Data: {session_date}\n"
            f"Hora: {session_time}\n"
            f"Duração: {duration_minutes} minutos\n"
            f"Local: {location}\n"
        )
        if notes:
            body += f"\nNotas adicionais: {notes}\n"

        try:
            resend.Email.create({
                "from": settings.email_from,
                "to": [trainer_email],
                "subject": f"Lembrete de treino - {client_name} amanhã às {session_time}",
                "text": body
            })
            logger.info(f"[EMAIL] ✅ Lembrete enviado para trainer {trainer_email}")

        except Exception as e:
            logger.error(f"[EMAIL] ❌ Erro ao enviar lembrete para trainer {trainer_email}: {e}")
            raise ValueError(f"Erro ao enviar email: {e}")