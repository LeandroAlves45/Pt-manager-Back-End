from __future__ import annotations

from sqlmodel import Session, select
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import logging

from app.db.models import session
from app.db.models import session
from app.db.models.session import TrainingSession, PackConsumption
from app.db.models.pack import ClientPack
from app.db.models.client import Client
from datetime import datetime
from app.services.notification_service import NotificationService
from app.utils.time import utc_now

logger = logging.getLogger(__name__)

class SessionService:
    """
        Regras de negócio relacionadas a sessões de treino.
    """

    @staticmethod
    def schedule_session (session: Session, client_id: str, *,starts_at: datetime , duration_minutes: int,
                          location: str | None = None, notes: str | None = None) -> TrainingSession:
        """
        Agenda uma nova sessão de treino para um cliente.
        """
        #verifica se o cliente existe
        client = session.get(Client, client_id)
        if not client:
            raise ValueError(f"Cliente com ID '{client_id}' não encontrado.")

        if client.archived_at is not None:
            raise ValueError("Não é possível agendar sessões para clientes arquivados.")
        
        now_dt = utc_now()

        #pack ativo com saldo
        active_pack = session.exec(
            select(ClientPack)
            .where(ClientPack.client_id == client_id)
            .where(ClientPack.archived_at.is_(None))
            .where(ClientPack.cancelled_at.is_(None))
            .where(ClientPack.sessions_used < ClientPack.sessions_total_snapshot)
            .where(or_(ClientPack.valid_until.is_(None), ClientPack.valid_until > now_dt))
            .order_by(ClientPack.purchase_at.desc())
            .limit(1)
        ).first()

        if not active_pack:
            raise ValueError("O cliente não tem packs ativos disponíveis. Não é possível agendar a sessão.")
        
        #impedir overbooking: verificar se já existe sessão agendada para o cliente na mesma data/hora
        remaining = active_pack.sessions_total_snapshot - active_pack.sessions_used

        future_scheduled_count = session.exec(
            select(func.count())
            .select_from(TrainingSession)
            .where(TrainingSession.client_id == client_id)
            .where(TrainingSession.status == "scheduled")
            .where(TrainingSession.starts_at >= now_dt)
        ).one()

        if future_scheduled_count >= remaining:
            raise ValueError("O cliente já tem sessões agendadas suficientes para o pack ativo. Não é possível agendar mais sessões.")
        
        new_session = TrainingSession(
            client_id=client_id,
            client_name=getattr(client, "full_name", None),
            starts_at=starts_at,
            duration_minutes=duration_minutes,
            location=location,
            notes=notes,
            status="scheduled",
        )
        
        try:
            
            session.add(new_session)
            session.flush()
            #cria notificações de lembrete para a sessão
            NotificationService.create_reminder_for_session(session, new_session)
            session.commit()

        except IntegrityError as e:
            session.rollback()
            raise ValueError("Erro ao agendar a sessão de treino.") from e
        
        except SQLAlchemyError as e:
            session.rollback()
            # Log técnico completo (stacktrace)
            logger.exception("Erro DB ao agendar sessão")
            raise ValueError("Erro ao agendar a sessão de treino.") from e
        
        session.refresh(new_session)
        return new_session
    
    @staticmethod
    def complete_session_consuming_pack(session: Session, session_id: str) -> TrainingSession:
        """
        Marca uma sessão como concluída e consome um pack do cliente.

        Garantias:
        -Idempotenência: marcar uma sessão como concluída várias vezes não consome múltiplos packs.
        -Transação: se não existir pack ativom, falha sem alterar estado
        """
        with session.begin():
            training_session = session.get(TrainingSession, session_id)
            if not training_session:
                raise ValueError(f"Sessão não existe.")

            #Se já está completed, tentamos garantir idempotenência
            # -se existir comsuption -> ok
            # -se não existir, ainda assim não devemos consumir á força sem consumo

            existing_consumption = session.exec(
                select(PackConsumption).where(PackConsumption.session_id == session_id)
            ).first()        

            if existing_consumption:
                #se já consumida; garante estado completed
                training_session.status = "completed"
                session.add(training_session)
                return training_session

            if training_session.status in ("cancelled", "missed"):
                raise ValueError("Não é possível completar uma sessão cancelada ou marcada como não comparecimento.")

            client_id = training_session.client_id

            #Encontrar o pack ativo
            now_dt = utc_now()

            active_pack = session.exec(
                select(ClientPack)  
                .where(ClientPack.client_id == client_id)   
                .where(ClientPack.archived_at.is_(None))
                .where(ClientPack.cancelled_at.is_(None))
                .where(ClientPack.sessions_used < ClientPack.sessions_total_snapshot)
                .where(or_(ClientPack.valid_until.is_(None), ClientPack.valid_until > now_dt))
                .order_by(ClientPack.purchase_at.desc())
                .limit(1)
            ).first()

            if not active_pack:
                raise ValueError("O cliente não tem packs ativos disponíveis para consumir.")
            
            #inserir consumption primeiro
            consumption = PackConsumption(session_id = session_id, client_pack_id=active_pack.id)
            session.add(consumption)

            #incrementar contador
            active_pack.sessions_used += 1
            session.add(active_pack)

            #marcar sessão como completed
            training_session.status = "completed"
            session.add(training_session)

            #flush para detetar IntegrityError antes do commit
            try:
                session.flush()
            except IntegrityError:
              # Se a constraint UNIQUE(session_id) existir, isto assegura idempotência em concorrência.
              # Recuperação: assume que alguém inseriu consumption primeiro.
                session.rollback()
                #Recarrega e devolve estado atual
                training_session = session.get(TrainingSession, session_id)
                if training_session:
                    training_session.status = "completed"
                    session.add(training_session)
                    session.commit()
                    return training_session
                raise

                 
            #fora do begin() faz commit
            session.refresh(training_session)
            return training_session
        
    #parte responsável pelo update da sessão
    @staticmethod
    def update_session(session: Session, session_id: str, *, starts_at: datetime | None = None,
                       duration_minutes: int | None = None, location: str | None = None,
                       notes: str | None = None, status: str | None = None) -> TrainingSession:
        """
        Atualiza os detalhes de uma sessão de treino.
        Se o horário (starts_at) for alterado:
        - Cancela notificações antigas
        - Cria novas notificações com horário atualizado
    
        Args:
            session: Sessão do banco de dados
            session_id: ID da sessão a atualizar
            starts_at: Nova data/hora (opcional)
            duration_minutes: Nova duração (opcional)
            location: Novo local (opcional)
            notes: Novas notas (opcional)
            status: Novo status (opcional - validado no controller)
        
       Returns:
            TrainingSession: Sessão atualizada
            
        Raises:
            ValueError: Se sessão não for encontrada
            SQLAlchemyError: Se houver erro no banco de dados ao atualizar a sessão
        """

        ts = session.get(TrainingSession, session_id)
        if not ts:
            raise ValueError(f"Sessão com ID '{session_id}' não encontrada.")
        
         # Se starts_at for alterado, precisamos atualizar as notificações
        horario_alterado = False
        old_starts_at = None

        if starts_at is not None and starts_at != ts.starts_at:
            horario_alterado = True
            old_starts_at = ts.starts_at
            logger.info(
            f"[SESSION UPDATE] Horário da sessão {session_id[:8]} será alterado: "
            f"{old_starts_at} → {starts_at}"
        )
            
            #cancelar notificações antigas
            if horario_alterado:
                cancelled_count = NotificationService.cancel_pending_reminders_for_session(session, session_id)
                logger.info(f"[SESSION UPDATE] {cancelled_count} notificações pendentes canceladas para sessão {session_id[:8]}")
            
            #atualizar campos da sessão
        if starts_at is not None:
            ts.starts_at = starts_at
        
        if duration_minutes is not None:
            ts.duration_minutes = duration_minutes
        
        if location is not None:
            ts.location = location

        if notes is not None:
            ts.notes = notes
        
        if status is not None:
            ts.status = status

        try:
            session.add(ts)
            session.flush()

            #criar novas notificações se o horário foi alterado
            if horario_alterado:
                new_notifications = NotificationService.create_reminder_for_session(session, ts)
                logger.info(f"[SESSION UPDATE] Novas notificações criadas para sessão {session_id[:8]} com horário atualizado {starts_at}.")
            
            session.commit()
        
        except IntegrityError as e:
            session.rollback()
            raise ValueError("Erro ao atualizar a sessão de treino.") from e
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.exception("Erro DB ao atualizar sessão")
            raise ValueError("Erro ao atualizar a sessão de treino.") from e
        
        session.refresh(ts)
        return ts
    
    #método para marcar sessão como missed
    @staticmethod
    def mark_session_missed(session: Session, session_id: str) -> TrainingSession:
        """
        Marca uma sessão como 'missed' (cliente faltou).
        
        Ações executadas:
        - Marca sessão como 'missed'
        - Cancela notificações pendentes (já não são necessárias)
        - Atualiza timestamp de modificação
        - Mantém histórico (não apaga)
        
        Regras de negócio:
        - Não pode marcar como missed uma sessão já completada
        - Não pode marcar como missed uma sessão já cancelada
        - Não consome pack (cliente faltou)
        
        Args:
            session: Sessão do banco de dados
            session_id: ID da sessão
            
        Returns:
            TrainingSession: Sessão atualizada
            
        Raises:
            ValueError: Se sessão não for encontrada ou validação falhar
            SQLAlchemyError: Se houver erro no banco de dados
        """

        #busca sessão
        ts = session.get(TrainingSession, session_id)
        if not ts:
            raise ValueError(f"Sessão com ID '{session_id}' não encontrada.")
        
        #validações  de regras de negócio
        if ts.status == "completed":
            raise ValueError("Não é possível marcar como falta uma sessão já concluída.")

        if ts.status == "cancelled":
            raise ValueError("Não é possível marcar como falta uma sessão já cancelada.")
        
        #se ja esta como "missed", garante idempotência
        if ts.status == "missed":
            logger.info(f"[SESSION MISSED] Sessão {session_id[:8]} já está marcada como falta")
            return ts
        
        logger.info(
        f"[SESSION MISSED] Marcando sessão {session_id[:8]} como falta. "
        f"Status anterior: {ts.status}"
    )
        #Cancelar notificações pendentes (se existirem)
        cancelled_count = NotificationService.cancel_pending_reminders_for_session(session, session_id)

        if cancelled_count > 0:
            logger.info(f"[SESSION MISSED] {cancelled_count} notificação(s) cancelada(s)"
                        f"(cliente faltou, não precisa mais lembrar) para sessão {session_id[:8]}")
            
        #atualizar status e timestamp
        ts.status = "missed"
        ts.updated_at = utc_now()

        try:
            session.add(ts)
            session.commit()
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.exception("Erro DB ao marcar sessão como missed")
            raise ValueError("Erro ao marcar a sessão como 'missed'.") from e
        
        session.refresh(ts)
        logger.info(f"[SESSION MISSED] Sessão {session_id[:8]} marcada como falta com sucesso.")
        return ts
    
    #método para marcar sessão como cancelled
    @staticmethod
    def cancel_session(session: Session, session_id: str) -> TrainingSession:
        """
        Marca uma sessão como 'cancelled' (cancelada).
        
        Ações executadas:
        - Marca sessão como 'cancelled'
        - Cancela notificações pendentes (já não são necessárias)
        - Atualiza timestamp de modificação
        - Mantém histórico (não apaga)
        
        Regras de negócio:
        - Não pode marcar como cancelled uma sessão já completada
        - Não pode marcar como cancelled uma sessão já marcada como falta
        - Não consome pack (sessão cancelada não é consumida)
        """

        #busca sessão
        ts = session.get(TrainingSession, session_id)
        if not ts:
            raise ValueError(f"Sessão com ID '{session_id}' não encontrada.")
        
        #validações  de regras de negócio
        if ts.status == "completed":
            raise ValueError("Não é possível cancelar uma sessão já concluída.")

        if ts.status == "missed":
            raise ValueError("Não é possível cancelar uma sessão marcada como falta.")
        
        #se ja esta como "cancelled", garante idempotência
        if ts.status == "cancelled":
            logger.info(f"[SESSION CANCELLED] Sessão {session_id[:8]} já está marcada como cancelada")
            return ts
        
        logger.info(
        f"[SESSION CANCELLED] Marcando sessão {session_id[:8]} como cancelada. "
        f"Status anterior: {ts.status}"
    )
        #Cancelar notificações pendentes (se existirem)
        cancelled_count = NotificationService.cancel_pending_reminders_for_session(session, session_id)

        if cancelled_count > 0:
            logger.info(f"[SESSION CANCELLED] {cancelled_count} notificação(s) cancelada(s)")
            
        #atualizar status e timestamp
        ts.status = "cancelled"
        ts.updated_at = utc_now()

        try:
            session.add(ts)
            session.commit()
        
        except SQLAlchemyError as e:
            session.rollback()
            logger.exception("Erro DB ao marcar sessão como cancelled")
            raise ValueError("Erro ao marcar a sessão como 'cancelled'.") from e
        
        session.refresh(ts)
        logger.info(f"[SESSION CANCELLED] Sessão {session_id[:8]} marcada como cancelada com sucesso.")
        return ts