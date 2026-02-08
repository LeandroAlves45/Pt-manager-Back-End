from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

class EmailService:
    """
        Serviço para envio de emails via SMTP.
    
        Suporta:
        - Gmail (smtp.gmail.com) - requer senha de app
        - Outlook (smtp-mail.outlook.com)
        - Outros servidores SMTP
    """
    @staticmethod
    def send_email(to_email: str, subject: str, body: str) -> None:
        """
        Envia email via SMTP configurado no .env
        
        Args:
            to_email: Email do destinatário
            subject: Assunto do email
            body: Corpo do email (texto simples)
            
        Raises:
            ValueError: Se configuração SMTP estiver incompleta
            smtplib.SMTPException: Se falhar ao enviar
        """
        if not all([settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password, settings.smtp_from_email]):
            error_msg = "Email não configurado. Defina SMTP_HOST, SMTP_USER, SMTP_PASSWORD no .env"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        #construir mensagem
        msg = MIMEText(body)
        msg["From"] = settings.smtp_from_email or settings.smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject

        #corpo de texto simples
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            logger.info(f"[EMAIL] Enviando email para {to_email}")

            #conectar e enviar email
            if settings.smtp_use_tls:
                 # Usar STARTTLS (porta 587)
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
                server.starttls()
            else:
                # Usar SSL direto (porta 465)
                server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20)

            #autenticar
            server.login(settings.smtp_user, settings.smtp_password)

            #enviar email
            server.send_message(msg)
            server.quit()

            logger.info(f"[EMAIL] Email enviado com sucesso para {to_email}")
        except smtplib.SMTPException:
            logger.error("Falha na autenticação SMTP - verifique SMTP_USER e SMTP_PASSWORD")
            raise ValueError("Credenciais SMTP inválidas")
        
        except smtplib.SMTPException as e:
            logger.error(f"Erro SMTP ao enviar email: {e}")
            raise ValueError(f"Erro ao enviar email: {e}")
            
        except Exception as e:
            logger.exception("Erro inesperado ao enviar email")
            raise ValueError(f"Erro inesperado: {e}")
