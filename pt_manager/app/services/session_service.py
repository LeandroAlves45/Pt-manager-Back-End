from __future__ import annotations

from sqlmodel import Session, select
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError


from app.db.models.session import TrainingSession, PackConsumption
from app.db.models.pack import ClientPack
from app.db.models.client import Client
from datetime import date
from app.utils.time import utc_now

class SessionService:
    """
        Regras de negócio relacionadas a sessões de treino.
    """

    @staticmethod
    def schedule_session (session: Session, client_id: str, *,starts_at: date , duration_minutes: int,
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
        session.add(new_session)
        try:
            session.commit()
            session.refresh(new_session)
        except IntegrityError as e:
            session.rollback()
            raise ValueError("Erro ao agendar a sessão de treino.") from e

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