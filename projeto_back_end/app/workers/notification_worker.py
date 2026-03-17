from __future__ import annotations

import argparse
import base64
import json
import time
from datetime import timezone
from email.message import EmailMessage
import smtplib
from urllib import request, parse
from typing import Optional

from sqlmodel import Session

from app.core.config import settings
from app.db.models.notification import Notification
from app.db.session import engine
from app.services.notification_service import NotificationService
from app.utils.time import utc_now_datetime

def send_email_smtp(*, to_email: str, subject: str, body: str) -> None:
    """
    Envio de email via SMTP.
    Requer:
    - SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL
    """
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password or not settings.smtp_from_email:
        raise ValueError("Configurações SMTP incompletas. Verifique as variáveis de ambiente.")
    
    msg = EmailMessage
    msg["From"] = settings.smtp_from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    if settings.smtp_use_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)


def send_whatsapp_twilio(*, to_phone: str, body: str) -> None:
    """
    Envio de WhatsApp via Twilio API.
    Requer:
    - TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
    """
    if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_whatsapp_from:
        raise ValueError("Configurações Twilio incompletas. Verifique as variáveis de ambiente.")
    
    #Garantir formato whatsapp:+1234567890
    to_value = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    payload = {
        "From": settings.twilio_whatsapp_from,
        "To": to_value,
        "Body": body
    }

    data = parse.urlencode(payload).encode("utf-8")
    req = request.Request(url, data=data, method="POST")

    #Basic Auth com Account SID e Auth Token
    auth = f"{settings.twilio_account_sid}:{settings.twilio_auth_token}".encode("utf-8")
    req.add_header("Authorization", f"Basic {base64.b64encode(auth).decode("ascii")}")

    with request.urlopen(req, timeout=15) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Erro ao enviar WhatsApp via Twilio: {response.status} {response.reason}")
        
def process_once(limit: int = 100) -> int:
    """
    Processa notificações pendentes que estão programadas para serem enviadas (scheduled_for <= now).
    Retorna o número de notificações processadas.
    """

    processed = 0

    with Session(engine) as db:
        due = NotificationService.list_due_notifications(db, limit=limit)

        for n in due:
            try:
                if n.channel == "email":
                    subject = "Lembrete de Treino"
                    send_email_smtp(
                        to_email=n.recipient,
                        subject="Lembrete de Treino",
                        body=n.message
                    )
                elif n.channel == "whatsapp":
                    send_whatsapp_twilio(
                        to_phone=n.recipient,
                        body=n.message
                    )
                else:
                    raise ValueError(f"Canal de notificação desconhecido: {n.channel}")
                
                n.status = "sent"
                n.send_at = utc_now_datetime()
                n.error_message = None

            except Exception as e:
                n.status = "failed"
                n.error_message = str(e)[:2000] #Limitar mensagem de erro a 2000 caracteres
            
            db.add(n)
            processed += 1
        
        db.commit()
    return processed

def main():
    parser = argparse.ArgumentParser(description="Worker para processar notificações de treino (pending -> sent/failed).")
    parser.add_argument("--loop", action="store_true", help="Executar em loop contínuo, verificando a cada minuto por novas notificações.")
    parser.add_argument("--limit", type=int, default=100, help="Número máximo de notificações a processar por execução.")
    args = parser.parse_args()

    if args.loop:
        while True:
            process_once(limit=args.limit)
            time.sleep(60) #Aguardar 1 minuto antes de verificar novamente
    else:
        process_once(limit=args.limit)

if __name__ == "__main__":
    main()