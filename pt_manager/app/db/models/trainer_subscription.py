"""
Modelo de subscrição do trainer.

Cada trainer tem exactamente uma linha nesta tabela.
É a fonte de verdade sobre o estado de acesso do trainer à plataforma.

Ciclo de vida de uma subscrição:
    1. Trainer regista-se → status="trialing", trial_end=hoje+15dias
    2. Trial acaba sem cartão → status="trial_expired" → acesso bloqueado
    3. Trainer adiciona cartão → Stripe cria subscrição → status="active"
    4. Pagamento falha → Stripe notifica via webhook → status="past_due"
    5. Grace period passa sem pagamento → status="cancelled" → acesso bloqueado

Tiers de preço (calculados com base em active_clients_count):
    FREE    →  0€   → 0-5  clientes ativos
    STARTER → 20€   → 6-49 clientes ativos
    PRO     → 40€   → 50+  clientes ativos
"""

import uuid
from typing import Optional
from datetime import date, datetime

from sqlmodel import Field, SQLModel
from app.utils.time import utc_now

#--------------------------------------------
# Constantes de status e tier
#--------------------------------------------

class SubscriptionStatus:
    """
    Estados possíveis de uma subscrição de trainer.
    """
    TRIALING = "trialing"           # Período de teste gratuito
    TRIAL_EXPIRED = "trial_expired" # Período de teste expirado, sem cartão
    ACTIVE = "active"               # Subscrição ativa e paga
    PAST_DUE = "past_due"           # Pagamento falhou, em período de carência
    CANCELLED = "cancelled"         # Subscrição cancelada ou expirada

    #Estados que permitem acesso à plataforma:
    ALLOWED = {TRIALING, ACTIVE, PAST_DUE}

class SubscriptionTier:
    """
    Tiers de preço com base no número de clientes ativos.
    """
    FREE = "free"       # 0-5 clientes ativos
    STARTER = "starter"   # 6-49 clientes ativos
    PRO = "pro"         # 50+ clientes ativos

class TrainerSubscription(SQLModel, table=True):
    """
    Modelo de subscrição do trainer.

    Relação 1:1 com User (role="trainer").
    Actualizada via webhooks do Stripe para manter o estado sincronizado.
    """

    __tablename__ = "trainer_subscriptions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True)

    #FK para trainer
    trainer_user_id: str = Field(foreign_key="users.id", unique=True, index=True)

    #estado atual da subscrição, usado para controlar o acesso do trainer à plataforma
    status: str = Field(default=SubscriptionStatus.TRIALING, index=True)

    #tier de preço, calculado com base no número de clientes ativos do trainer
    tier: str = Field(default=SubscriptionTier.FREE, index=True)

    #Data de fim do período de trial (15 dias após registo), usada para bloquear acesso se o trainer não adicionar cartão a tempo
    trial_end: Optional[date] = Field(default=None, index=True)
    current_period_end: Optional[date] = Field(default=None, index=True)

    #REFERÊNCIAS STRIPE
    #Criado no momento do registo, antes de qualquer pagamento
    stripe_customer_id: Optional[str] = Field(default=None, index=True)

    #ID da subscrição no Stripe, preenchido quando o trainer adiciona cartão e a subscrição é criada
    stripe_subscription_id: Optional[str] = Field(default=None, index=True)

    #ID do price do Stripe, usado para identificar o plano de pagamento (FREE, STARTER, PRO) e calcular o valor a cobrar
    stripe_price_id: Optional[str] = Field(default=None, index=True)

    #Constagem dos clientes ativos
    #Actualizado sempre que um cliente é adicionado ou arquivado do trainer, para calcular o tier de preço e o valor a cobrar
    active_clients_count: int = Field(default=0, ge=0)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)