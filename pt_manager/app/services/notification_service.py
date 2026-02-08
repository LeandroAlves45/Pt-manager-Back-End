from __future__ import annotations
from datetime import timedelta, datetime, timezone
from typing import Optional
from sqlmodel import Session, select

from app.core.config import settings
from app.db.models.notification import Notification , NotificationChannel, RecipientType, NotificationStatus
from app.db.models.session import TrainingSession
from app.db.models.client import Client
from app.utils.time import utc_now_datetime, local_date_to_utc_datetime


class NotificationService:
    """
    Regras de negócio de notificações:
    - criar lembretes (T-1 dia) quando uma sessão é agendada
    - cancelar lembretes pendentes quando necessário
    - listar pendentes para o worker processar
    """

    @staticmethod
    def _compute_reminder_datetime_utc(training_session: TrainingSession):
        """
        Calcula a data e hora UTC para enviar o lembrete, com base na data da sessão e nas configurações de fuso horário e hora local.
        """

        remind_local_date = training_session.starts_at.date() - timedelta(days=1)

        #Debug: para testes, pode ser útil enviar lembrete em T-1 minuto:
        scheduled_for_utc = datetime.now(timezone.utc) + timedelta(minutes=1)
        return scheduled_for_utc

        #converte "data local + hora local" para UTC
        #scheduled_for_utc = local_date_to_utc_datetime(
            #remind_local_date,
            #hour=settings.reminder_hour_local,
            #minute=0,
            #tz_str=settings.timezone
        #)
        #return scheduled_for_utc
    
    @staticmethod
    def create_reminder_for_session(db: Session, training_session: TrainingSession) -> list[Notification]:
        """
        Cria:
        - WhatsApp para o cliente
        - Email para o PT

        Nota: se scheduled_for já passou, não cria (evita spam imediato).
        """
        now_utc = utc_now_datetime()
        scheduled_for = NotificationService._compute_reminder_datetime_utc(training_session)

        if scheduled_for <= now_utc:
            #se a sessão foi marcada "tarde demais" para T-1, simplesmente não cria notificação (evita spam imediato)
            return []

        client = db.get(Client, training_session.client_id)
        if not client:
            raise ValueError("Cliente não encontrado para a sessão.")

        notifications: list[Notification] = []

        #---Whatsapp para cliente---

        if client.phone:
            msg_client = (
                f"Olá {client.name}, este é um lembrete de que tem uma sessão de treino agendada para "
                f"{training_session.starts_at} com duração de {training_session.duration_minutes} minutos. "
                "Prepare-se para um ótimo treino!"
            )
            notifications.append(
                Notification(
                    session_id=training_session.id,
                    channel=NotificationChannel.WHATSAPP,
                    recipient_type=RecipientType.CLIENT,
                    recipient=client.phone,
                    message=msg_client,
                    scheduled_for=scheduled_for,
                    status=NotificationStatus.PENDING
                )
            )
        
        #---Email para o PT---
        if settings.trainer_email:
            masg_trainer = (
                f"Lembrete: treino amanhã com {client.full_name}."
                f"Data: {training_session.starts_at}."
                f"Duração: {training_session.duration_minutes} minutos."
            )
            notifications.append(
                Notification(
                    session_id=training_session.id,
                    channel=NotificationChannel.EMAIL,
                    recipient_type=RecipientType.TRAINER,
                    recipient=settings.trainer_email,
                    message=masg_trainer,
                    scheduled_for=scheduled_for,
                    status=NotificationStatus.PENDING
                )
            )

        #persistir notificações
        for notification in notifications:
            db.add(notification)
        
        db.flush()
        return notifications
    
    @staticmethod
    def cancel_pending_reminders_for_session(db: Session, session_id: str) -> int:
        """
        Cancela notificações pendentes associadas a uma sessão (ex: sessão cancelada ou remarcada).
        Retorna o número de notificações canceladas.
        """
        statement = (
            select(Notification)
            .where(Notification.session_id == session_id)
            .where(Notification.status == NotificationStatus.PENDING)
        ).all()
        
        for notification in statement:
            notification.status = NotificationStatus.CANCELLED
            db.add(notification)
        
        db.flush()
        return len(statement)
    
    @staticmethod
    def list_due_notifications(db: Session, *, limit: int = 100) -> list[Notification]:
        """
        Lista notificações pendentes que estão programadas para serem enviadas (scheduled_for <= now).
        """
        now_utc = utc_now_datetime()

        return db.exec(
            select(Notification)
            .where(Notification.status == NotificationStatus.PENDING)
            .where(Notification.scheduled_for <= now_utc)
            .order_by(Notification.scheduled_for.asc())
            .limit(limit)
        ).all()
