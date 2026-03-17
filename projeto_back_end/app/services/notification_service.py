from __future__ import annotations
from datetime import time, timedelta, datetime, timezone
import logging
from typing import Optional
from sqlmodel import Session, select
import pytz

from app.core.config import settings
from app.db.models.notification import Notification , NotificationChannel, RecipientType, NotificationStatus
from app.db.models.session import TrainingSession
from app.db.models.client import Client
from app.db.models.user import User
from app.utils.time import utc_now_datetime

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Serviço de notificações via EMAIL.
    
    Sistema simplificado usando apenas email com templates HTML profissionais.
    WhatsApp foi removido para manter o código simples e funcional.
    """

    @staticmethod
    def _compute_reminder_datetime_utc(training_session: TrainingSession) -> datetime:
        """
        Calcula o datetime UTC para enviar o lembrete.
        
        MODO PRODUÇÃO: 1 dia antes às 20h (horário local)
        MODO TESTE: X minutos após o agendamento (configurável via .env)
        
        Args:
            training_session: A sessão de treino para a qual criar o lembrete
        
        Returns:
            datetime: O momento em UTC quando o lembrete deve ser enviado
        """
        
        # Verificar se está em modo de teste (via variável de ambiente)
        test_mode = getattr(settings, 'notification_test_mode', False)
        test_minutes = getattr(settings, 'notification_test_minutes', 2)
        
        if test_mode:
            # ====================================
            # MODO TESTE: Enviar em X minutos
            # ====================================
            scheduled_for_utc = datetime.now(timezone.utc) + timedelta(minutes=test_minutes)
            
            logger.info(
                f"[NOTIFICAÇÃO TEST MODE] Sessão {training_session.id[:8]} - "
                f"Notificação agendada para {scheduled_for_utc.strftime('%H:%M:%S')} UTC "
                f"(daqui a {test_minutes} minutos)"
            )
            
            return scheduled_for_utc
        
        else:
            # ====================================
            # MODO PRODUÇÃO: 1 dia antes às 20h
            # ====================================
            
            # Extrair apenas a data do starts_at (que agora é datetime)
            session_date = training_session.starts_at.date()
            
            # Calcular a data do lembrete (1 dia antes da sessão)
            reminder_date = session_date - timedelta(days=1)
            
            # Criar datetime às 20h no horário local (Europe/Lisbon)
            local_tz = pytz.timezone(settings.timezone)
            remind_local_dt = local_tz.localize(
                datetime.combine(reminder_date, time(20, 0))
            )
            
            # Converter para UTC para armazenamento na base de dados
            scheduled_for_utc = remind_local_dt.astimezone(pytz.UTC)
            
            logger.info(
                f"[NOTIFICAÇÃO PRODUÇÃO] Sessão {training_session.id[:8]} - "
                f"Notificação agendada para {scheduled_for_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC "
                f"(1 dia antes às 20h local)"
            )
            
            return scheduled_for_utc
    
    @staticmethod
    def create_reminder_for_session(db: Session, training_session: TrainingSession) -> list[Notification]:
        """
        Cria:
        - Email para o PT

        Nota: se scheduled_for já passou, não cria (evita spam imediato).
        """
        now_utc = utc_now_datetime()
        scheduled_for = NotificationService._compute_reminder_datetime_utc(training_session)

        # Verificar se já passou do horário
        if scheduled_for <= now_utc:
            logger.warning(
                f"[NOTIFICAÇÃO] Sessão {training_session.id[:8]} agendada tarde demais. "
                f"Notificação NÃO criada para evitar spam."
            )
            return []

        #buscar dados do cliente para personalizar mensagem
        client = db.get(Client, training_session.client_id)
        if not client:
            raise ValueError("Cliente não encontrado para a sessão.")

        notifications: list[Notification] = []

        #---Email para cliente---

        if client.email:

            # Preparar dados para o template HTML
            session_date = training_session.starts_at.strftime("%d/%m/%Y")
            session_time = training_session.starts_at.strftime("%H:%M")

            trainer = db.get(User, training_session.owner_trainer_id)
            logo_url = trainer.logo_url or ""

            # Mensagem estruturada para o scheduler processar
            msg_client = (
                f"TEMPLATE_HTML|"
                f"client_name={client.full_name}|"
                f"session_date={session_date}|"
                f"session_time={session_time}|"
                f"duration_minutes={training_session.duration_minutes}|"
                f"location={training_session.location or 'A definir'}|"
                f"trainer_logo_url={logo_url}"  
            )
            notifications.append(
                Notification(
                    session_id=training_session.id,
                    channel=NotificationChannel.EMAIL,
                    recipient_type=RecipientType.CLIENT,
                    recipient=client.email,
                    message=msg_client,
                    scheduled_for=scheduled_for,
                    status=NotificationStatus.PENDING
                )
            )

            logger.info(f"[NOTIFICAÇÃO] ✅ Email HTML criado para cliente {client.email}")
        else:
            logger.warning(f"[NOTIFICAÇÃO] ⚠️  Cliente {client.id[:8]} não tem email cadastrado")
        
        #---Email para o PT---
        if settings.trainer_email:
            session_datetime_str = training_session.starts_at.strftime("%d/%m/%Y às %H:%M")

            msg_trainer = (
                f"🏋️ Lembrete: Treino Amanhã\n\n"
                f"Cliente: {client.full_name}\n"
                f"Data/Hora: {session_datetime_str}\n"
                f"Duração: {training_session.duration_minutes} minutos\n"
                f"Local: {training_session.location or 'Online'}\n"
            )

            if training_session.notes:
                msg_trainer += f"Notas: {training_session.notes}\n"

            notifications.append(
                Notification(
                    session_id=training_session.id,
                    channel=NotificationChannel.EMAIL,
                    recipient_type=RecipientType.TRAINER,
                    recipient=settings.trainer_email,
                    message=msg_trainer,
                    scheduled_for=scheduled_for,
                    status=NotificationStatus.PENDING
                )
            )

            logger.info(f"[NOTIFICAÇÃO] ✅ Email criado para PT {settings.trainer_email}")
        else:
            logger.warning("[NOTIFICAÇÃO] ⚠️  TRAINER_EMAIL não configurado no .env")

        #persistir notificações
        for notification in notifications:
            db.add(notification)
        
        db.flush()

        logger.info(
            f"[NOTIFICAÇÃO] 📧 {len(notifications)} email(s) criado(s). "
            f"Envio agendado para: {scheduled_for.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
        return notifications
    
    @staticmethod
    def cancel_pending_reminders_for_session(db: Session, session_id: str) -> int:
        """
        Cancela notificações pendentes de uma sessão.
        
        Útil quando:
        - Sessão é cancelada
        - Sessão é remarcada
        
        Args:
            db: Sessão do banco de dados
            session_id: ID da sessão
            
        Returns:
            int: Número de notificações canceladas
        """
        statement = db.exec(
            select(Notification)
            .where(Notification.session_id == session_id)
            .where(Notification.status == NotificationStatus.PENDING)
        ).all()
        
        for notification in statement:
            notification.status = NotificationStatus.CANCELLED
            db.add(notification)
        
        db.flush()

        logger.info(
            f"[NOTIFICAÇÃO] ❌ {len(statement)} notificação(ões) cancelada(s) "
            f"para sessão {session_id[:8]}"
        )
        return len(statement)
    
    @staticmethod
    def list_due_notifications(db: Session, *, limit: int = 100) -> list[Notification]:
        """
        Lista notificações pendentes que estão programadas para serem enviadas (scheduled_for <= now).
        """
        now_utc = utc_now_datetime()

        notifications = db.exec(
            select(Notification)
            .where(Notification.status == NotificationStatus.PENDING)
            .where(Notification.scheduled_for <= now_utc)
            .order_by(Notification.scheduled_for.asc())
            .limit(limit)
        ).all()

        if notifications:
            logger.info(
                f"[NOTIFICAÇÃO] 📬 {len(notifications)} email(s) pronto(s) para envio"
            )

        return notifications
