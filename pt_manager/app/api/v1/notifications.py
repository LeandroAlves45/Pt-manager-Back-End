from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db.session import db_session
from app.db.models.notification import Notification
from app.services.email_service import EmailService
from app.services.whatsapp_service import WhatsAppService

router = APIRouter(prefix="/notifications", tags=["notifications"])

@router.post("/dispatch")
def dispach_due_notifications(session: Session = Depends(db_session)) -> dict:
    #Endpoint para o worker process chamar periodicamente (ex: a cada 5 minutos) e disparar notificações pendentes.

    now = datetime.now(timezone.utc)

    #busca notificações pendentes (scheduled_for <= now)
    stmt = select(Notification).where(
        Notification.status == "pending",
        Notification.scheduled_for <= now,
    )
    notifications_to_send = session.exec(stmt).all()

    sent= 0
    failed = 0

    for notification in notifications_to_send:
        try:
            recipient =(notification.recipient or "").strip()

            #heurística simples para validar destinatário (ex: número de telefone para WhatsApp, email para email)
            if "@" in recipient:
                #email para trainer
                EmailService.send_notification(
                    to_email=recipient,
                    subject="Lembrete de Treino",
                    body=notification.message
                )
            else:
                #WhatsApp para cliente
                WhatsAppService.send_message(
                    to_phone=recipient,
                    message=notification.message
                )
           #marca como enviado
            notification.status = "sent"
            notification.sent_at= now
            notification.error_message = None
            sent += 1

        except Exception as e:
            #Marca como falhada e guarda erro
            notification.status = "failed"
            notification.error_message = str(e)
            failed += 1
    
    session.commit()
    return {"due_found": len(notifications_to_send), "sent": sent, "failed": failed}