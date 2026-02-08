from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from datetime import datetime, timezone
from sqlmodel import Session, select
import logging

from app.core.config import settings
from app.db.session import engine
from app.db.models.notification import Notification, NotificationStatus
from app.services.email_service import EmailService
from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)

jobstores = {
    'default': SQLAlchemyJobStore(url='sqlite:///scheduler_jobs.db')  # Armazenamento dos jobs em SQLite local
}

scheduler = BackgroundScheduler()

def dispatch_job():

    """
    Job executado periodicamente para enviar notificações pendentes.
    
    Fluxo:
    1. Busca notificações com status=pending e scheduled_for <= agora
    2. Tenta enviar via canal apropriado (email ou WhatsApp)
    3. Atualiza status para sent/failed conforme resultado
    4. Registra erro em error_message se falhar
    """
    now = datetime.now(timezone.utc)
    logger.info(f"[SCHEDULER] Iniciando job de dispatch às {now}")

    with Session(engine) as session:
        stmt = select(Notification).where(
            Notification.status == NotificationStatus.PENDING,
            Notification.scheduled_for <= now,
        )
        notifications= session.exec(stmt).all()

        logger.info(f"[SCHEDULER] Encontradas {len(notifications)} notificações para enviar")
        
        for notification in notifications:
            try:
                recipient =(notification.recipient or "").strip()

                if not recipient:
                    raise ValueError("Destinatário vazio")

                #heurística simples para validar destinatário (ex: número de telefone para WhatsApp, email para email)
                if "@" in recipient:
                    #email para trainer
                    logger.info(f"[EMAIL] Enviando para {recipient}")
                    EmailService.send_email(
                        to_email=recipient,
                        subject="Lembrete de Treino - PT Manager",
                        body=notification.message
                    )
                else:
                    #WhatsApp para cliente
                    logger.info(f"[WHATSAPP] Enviando para {recipient}")
                    WhatsAppService.send_message(
                        to_phone=recipient,
                        body=notification.message
                    )
               #marca como enviado
                notification.status = NotificationStatus.SENT
                notification.sent_at= now
                notification.error_message = None
                logger.info(f"[SUCCESS] Notificação {notification.id} enviada com sucesso")

            except Exception as e:
                #Marca como falhada e guarda erro
                notification.status = NotificationStatus.FAILED
                notification.error_message = str(e)[:1000]  # Limitar tamanho do erro para evitar problemas de armazenamento
                logger.error(
                    f"[FAILED] Erro ao enviar notificação {notification.id}: {e}",
                    exc_info=True
                )
        
        session.commit()
        logger.info(f"[SCHEDULER] Dispatch_job concluído")

def start_scheduler():
    """
    Inicia o scheduler em background.
    
    Configuração:
    - Executa dispatch_job a cada 60 segundos
    - Persiste jobs em SQLite para sobreviver a restarts
    - Replace_existing=True para evitar duplicação em restart
    """

    logger.info("[SCHEDULER] Iniciando scheduler de notificações")

    scheduler.add_job(dispatch_job, IntervalTrigger(seconds=60), id="notification_dispatch", replace_existing=True, max_instances=1)
    scheduler.start()
    logger.info("[SCHEDULER] Scheduler iniciado com sucesso")

def shutdown_scheduler():
    """
    Função para desligar o scheduler graciosamente (ex: em shutdown da aplicação).
    """
    logger.info("[SCHEDULER] Desligando scheduler de notificações")
    scheduler.shutdown(wait=False)
    logger.info("[SCHEDULER] Scheduler desligado")