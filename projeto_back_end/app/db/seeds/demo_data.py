"""
Seed de demonstração — cria apenas o trainer de teste.
 
O que é criado:
    TRAINER DEMO
        User (role="trainer", is_exempt_from_billing=True)
        TrainerSubscription (status="active", tier="pro")
        TrainerSettings (cor primária, nome da app)
 
O cliente é criado manualmente pelo trainer via dashboard.
Isto evita a complexidade de gerir FKs entre User, Client e checkins
na seed, que causava falhas parciais difíceis de recuperar.
 
Credenciais de acesso:
    Trainer  → DEFAULT_TRAINER_EMAIL  / DEFAULT_TRAINER_PASSWORD
 
Idempotência:
    Verifica cada peça individualmente — apenas cria o que não existe.
    Seguro de executar em cada reinício.
 
Apenas activo se SEED_DEMO_DATA=true estiver definido.
"""

import logging
from datetime import date
from sqlmodel import Session, select
from sqlalchemy import text

from app.db.models.user import User

from app.db.models.trainer_subscription import (
    TrainerSubscription, SubscriptionStatus, SubscriptionTier
)
from app.core.security import hash_password
from app.core.config import settings

logger = logging.getLogger(__name__)

def seed_demo_data(session: Session) -> None:
    """
    Cria o trainer de demonstração se ainda não existirem.

    Só corre se SEED_DEMO_DATA=true estiver nas variáveis de ambiente.
    """

    # Guarda de segurança — não cria dados de demo sem configuração explícita
    if not settings.seed_demo_data:
        logger.info("SEED_DEMO_DATA não está definido como 'true'. Saltando seed de demonstração.")
        return

    trainer_email = settings.default_trainer_email
    trainer_pass = settings.default_trainer_password
    trainer_name = settings.default_trainer_name
    

    # Todas as variáveis do trainer têm de estar preenchidas
    if not trainer_email or not trainer_pass or not trainer_name:
        logger.warning(
            "[SEED DEMO] DEFAULT_TRAINER_EMAIL, DEFAULT_TRAINER_PASSWORD ou "
            "DEFAULT_TRAINER_NAME não estão definidos. A saltar."
        )
        return

    # ------------------------------------------------------------------
    # Identificar o que já existe (idempotência granular)
    # ------------------------------------------------------------------
    # Cada bloco abaixo cria APENAS o que ainda não existe na BD.
    # Isto garante que falhas parciais são auto-corrigidas no próximo deploy.

    trainer_user  = session.exec(select(User).where(User.email == trainer_email)).first()

        # ==================================================
        # Personal Trainer Demo
        # ==================================================

    if not trainer_user:
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
        logger.info(f"[SEED DEMO] Trainer User criado: {trainer_email}")
    else:
        logger.info(f"[SEED DEMO] Trainer User já existe: {trainer_email}")

    # ==================================================
    # TrainerSubscription
    # Cria a subscrição do trainer se não existir
    # ==================================================

    existing_sub = session.exec(
        select(TrainerSubscription).where(TrainerSubscription.trainer_user_id == trainer_user.id)
    ).first()

    if not existing_sub:
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
        logger.info("[SEED DEMO] TrainerSubscription criada.")

    # ==================================================
    # TrainerSettings
    # Cria as definições de branding se não existirem
    # ==================================================

    try:
        from app.db.models.trainer_settings import TrainerSettings

        existing_settings = session.exec(
            select(TrainerSettings).where(TrainerSettings.trainer_user_id == trainer_user.id)
        ).first()

        if not existing_settings:
            trainer_settings = TrainerSettings(
                trainer_user_id=trainer_user.id,
                primary_color="#00A8E8",  # Azul
                app_name="PT Manager Demo",
                timezone="Europe/Lisbon",
            )
            session.add(trainer_settings)
            logger.info("[SEED DEMO] TrainerSettings criadas.")

    except ImportError:
        logger.warning("[SEED DEMO] TrainerSettings não disponível via import.")


    try:
        session.commit()
        logger.info(f"[SEED DEMO] Trainer demo pronto: {trainer_email} / {trainer_pass}")
        logger.info("[SEED DEMO] Cria o cliente manualmente via dashboard do trainer.")
    except Exception as e:
        session.rollback()
        logger.error(f"[SEED DEMO] Erro ao criar trainer demo: {str(e)}")
        raise
