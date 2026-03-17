"""
Seed de demonstração — cria um trainer e um cliente de teste.
 
Objectivo: permitir testar os 3 dashboards imediatamente após deploy,
sem ter de criar dados manualmente via API.
 
O que é criado:
    TRAINER DEMO
        User (role="trainer", is_exempt_from_billing=True)
        TrainerSubscription (status="active", tier="pro")
        TrainerSettings (cor primária, nome da app)
 
    CLIENTE DEMO
        Client (presencial, ligado ao trainer demo)
        User (role="client", ligado ao Client)
        CheckIn (status="pending") — para o dashboard do cliente mostrar alerta
 
Credenciais de acesso:
    Trainer  → DEMO_TRAINER_EMAIL  / DEMO_TRAINER_PASSWORD
    Cliente  → DEMO_CLIENT_EMAIL   / DEMO_CLIENT_PASSWORD
 
Comportamento idempotente:
    Verifica os emails antes de criar — seguro de executar em cada reinício.
    Se qualquer um dos utilizadores já existir, a seed é ignorada na íntegra.
 
Apenas activa se a variável SEED_DEMO_DATA=true estiver definida.
Isto evita criar dados de teste em produção real por acidente.
"""

import logging
from datetime import date
from sqlmodel import Session, select
from sqlalchemy import text

from app.db.models.user import User
from app.db.models.client import Client
from app.db.models.trainer_subscription import (
    TrainerSubscription, SubscriptionStatus, SubscriptionTier
)
from app.db.models.checkin import CheckIn
from app.core.security import hash_password
from app.core.config import settings

logger = logging.getLogger(__name__)

def seed_demo_data(session: Session) -> None:
    """
    Cria o trainer e cliente de demonstração se ainda não existirem.

    Só corre se SEED_DEMO_DATA=true estiver nas variáveis de ambiente.
    """

    # Guarda de segurança — não cria dados de demo sem configuração explícita
    if not settings.seed_demo_data:
        logger.info("SEED_DEMO_DATA não está definido como 'true'. Saltando seed de demonstração.")
        return

    trainer_email = settings.demo_trainer_email
    trainer_pass = settings.demo_trainer_password
    trainer_name = settings.demo_trainer_name

    client_email = settings.demo_client_email
    client_pass = settings.demo_client_password
    client_name = settings.demo_client_name

    # Verifica se já existem — se qualuqer um dos dois já existir, não cria nenhum
    existing_trainer = session.exec(select(User).where(User.email == trainer_email)).first()
    existing_client = session.exec(select(User).where(User.email == client_email)).first()

    if existing_trainer or existing_client:
        logger.info("Trainer ou cliente de demonstração já existe. Saltando criação.")
        return
    
    logger.info("[SEED DEMO] _A criar dados de demonstração...")

    try:

        # ==================================================
        # Personal Trainer Demo
        # ==================================================

        trainer_user = User(
            email=trainer_email,
            hashed_password=hash_password(trainer_pass[:72]),
            full_name=trainer_name,
            role="trainer",
            is_active=True,
            is_exempt_from_billing=True
        )
        session.add(trainer_user)
        session.flush()  # Para obter o ID do trainer_user

        # Subscrição ativa no tier Pro
        subscription = TrainerSubscription(
            trainer_user_id=trainer_user.id,
            status=SubscriptionStatus.ACTIVE,
            tier=SubscriptionTier.PRO,
            active_clients_count=1,  # Para mostrar o limite de clientes no dashboard
            trial_end=None,
            stripe_customer_id=None,
            stripe_subscription_id=None,
        )
        session.add(subscription)

        # TrainerSettings - cor primária e nome da app personalizados
        try:
            from app.db.models.trainer_settings import TrainerSettings
            trainer_settings = TrainerSettings(
                trainer_user_id=trainer_user.id,
                primary_color="#00A8E8",  # Azul
                app_name="PT Manager Demo",
                timezone="Europe/Lisbon",
            )
            session.add(trainer_settings)
        except ImportError:
            import uuid
            session.exec(text(f"""
                INSERT INTO trainer_settings
                    (id, trainer_user_id, primary_color, app_name, timezone, created_at, updated_at)
                VALUES
                    ('{str(uuid.uuid4())}', '{trainer_user.id}', '#00A8E8', 'PT Manager Demo',
                     'Europe/Lisbon', NOW(), NOW())
                ON CONFLICT (trainer_user_id) DO NOTHING
            """))

        # ==================================================
        # Cliente Demo
        # ==================================================

        # Registo do cliente 
        client = Client(
            full_name=client_name,
            email=client_email,
            phone="910710373",
            birth_date=date(1990, 1, 1),
            sex="F",
            height_cm=165,
            training_modality="presencial",
            objetive="Perder massa gorda e tonificar",
            notes="Cliente demo criado para fins de teste. Não é um cliente real.",
        )
        session.add(client)
        session.flush()  # Para obter o ID do cliente

        # owner_trainer_id não está declarado no modelo ORM Client
        session.exec(
            text(f"UPDATE clients SET owner_trainer_id = '{trainer_user.id}' WHERE id = '{client.id}'")
        )

        # Utilizado do cliente — para fazer login e mostrar o dashboard do cliente

        client_user = User(
            email=client_email,
            hashed_password=hash_password(client_pass[:72]),
            full_name=client_name,
            role="client",
            is_active=True,
            client_id=client.id,
        )
        session.add(client_user)

        # ==================================================
        # Check-in pendente 
        # ==================================================

        checkin = CheckIn(
            client_id=client.id,
            requested_by_trainer_id=trainer_user.id,
            status="pending",
        )
        session.add(checkin)

        session.commit()

        logger.info(f"[SEED DEMO] Trainer criado: {trainer_email} / {trainer_pass}")
        logger.info(f"[SEED DEMO] Cliente criado: {client_email} / {client_pass}")
        logger.info("[SEED DEMO] Dados de demonstração criados com sucesso.")

    except Exception as e:
        session.rollback()
        logger.error(f"[SEED DEMO] Erro ao criar dados de demonstração: {e}")
        raise