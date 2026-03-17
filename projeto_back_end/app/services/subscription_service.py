"""
Serviço de subscrições — lógica de negócio de tiers e controlo de acesso.

Este serviço contém a inteligência do sistema de billing:
    - Calcular em que tier um trainer está com base no nº de clientes
    - Decidir se um trainer pode adicionar mais clientes
    - Fazer upgrade/downgrade automático no Stripe quando o nº de clientes muda
    - Verificar se um trainer tem acesso activo à plataforma
"""

from datetime import date, datetime, timezone
from typing import Optional

from sqlmodel import Session, select
from sqlalchemy import func

from app.db.models.trainer_subscription import TrainerSubscription, SubscriptionStatus, SubscriptionTier
from app.db.models.client import Client
from app.services.stripe_service import StripeService
from app.core.config import settings

#--------------------------------------------
# Definição dos tiers e limites
#--------------------------------------------

TIER_CONFIG = {
    SubscriptionTier.FREE: {"max_clients": 5, "price_id": settings.stripe_price_free, "monthly_eur": 0},
    SubscriptionTier.STARTER: {"max_clients": 49, "price_id": settings.stripe_price_starter, "monthly_eur": 20},
    SubscriptionTier.PRO: {"max_clients": None, "price_id": settings.stripe_price_pro, "monthly_eur": 40},
}

class SubscriptionService:

    @staticmethod
    def get_tier_for_count(client_count: int) -> str:
        """
        Determina o tier correcto com base no nº de clientes activos.

        Esta é a função central da lógica de pricing.
        Qualquer alteração nos limites de tier deve ser feita aqui.

        Exemplos:
            0  clientes → FREE
            5  clientes → FREE
            6  clientes → STARTER
            49 clientes → STARTER
            50 clientes → PRO
        """
        if client_count <= 5:
            return SubscriptionTier.FREE
        elif client_count <= 49:
            return SubscriptionTier.STARTER
        else:
            return SubscriptionTier.PRO
        
    @staticmethod
    def can_add_client(subscription: Optional[TrainerSubscription]) -> tuple[bool, str]:
        """
        Verifica se o trainer pode adicionar mais um cliente.

        Retorna uma tupla (pode_adicionar, mensagem_de_erro).
        A mensagem só é relevante quando pode_adicionar=False.

        Regras:
            - Trial: pode adicionar até ao limite do tier FREE (5)
            - Active STARTER: pode até 49
            - Active PRO: sem limite
            - Trial expirado / cancelado: não pode adicionar
        """

        if not subscription:
            return False, "Sem subscrição ativa. Por favor, cria uma subscrição para poderes adicionar clientes."

        if subscription.status == SubscriptionStatus.TRIAL_EXPIRED:
            return False, (
                "O teu período de trial expirou. "
                "Adiciona um método de pagamento para reactivar a tua subscrição e continuares a usar a plataforma."
            )
        
        if subscription.status == SubscriptionStatus.CANCELLED:
            return False, (
                "A tua subscrição foi cancelada."
                "Adiciona um método de pagamento para reactivar a tua subscrição e continuares a usar a plataforma."
            )
        
        #Verifica primeiro se a subscrição está activa (trial ou paga)
        if subscription.status not in SubscriptionStatus.ALLOWED:
            return False, "Subscrição inactiva. Por favor, adicione um método de pagamento para activar a sua subscrição."
        
        #Verifica o tier actual e os clientes activos
        current_tier_config = TIER_CONFIG[subscription.tier]
        max_clients = current_tier_config["max_clients"]

        #PRO não tem limite
        if max_clients is None:
            return True, ""
        
        #Verifica se já atingiu o limite do tier
        if subscription.active_clients_count >= max_clients:
            next_tier_msg = _get_upgrade_message(subscription.tier)
            return False,( 
                f"Limite de clientes atingido para o tier {subscription.tier.upper()}."
                f"Podes adicionar mais clientes fazendo upgrade para o próximo tier. {next_tier_msg}"
            )
        
        if subscription.status == SubscriptionStatus.TRIALING:
            remaining = max_clients - subscription.active_clients_count
            return True, (
                f"Estás em período de trial."
                f"Podes adicionar mais {remaining} cliente/s durante o trial."
            )
        
        if subscription.status == SubscriptionStatus.PAST_DUE:
            return True, (
                "A tua subscrição está com pagamento em atraso."
                "Por favor, atualize o método de pagamento para reactivar a tua subscrição e continuares a usar a plataforma."
            )
        
        return True, ""
    
    @staticmethod
    def sync_client_count(
        session: Session, 
        trainer_user_id: str, 
    ) -> TrainerSubscription:
        """
        Reconta os clientes activos do trainer e sincroniza o tier no Stripe se necessário.

        Chamado sempre que:
            - Um cliente é criado (count +1)
            - Um cliente é arquivado (count -1)
            - Um cliente é reactivado (count +1)

        Processo:
            1. Faz COUNT(*) dos clientes activos deste trainer
            2. Calcula o tier correcto para esse count
            3. Se o tier mudou → actualiza no Stripe
            4. Actualiza a linha trainer_subscriptions na BD

        Usar COUNT na BD em vez de incrementar/decrementar o cache
        para garantir consistência mesmo se houver operações concorrentes.
        """
        #Conta clientes activos
        count = session.exec(
            select(func.count()).select_from(Client).where(
                Client.owner_trainer_id == trainer_user_id,
                Client.archived_at.is_(None)
            )
        ).one()

        #Busca subscrição do trainer
        subscription = session.exec(
            select(TrainerSubscription).where(TrainerSubscription.trainer_user_id == trainer_user_id)
        ).first()

        if not subscription:
            return None
        
        new_tier = SubscriptionService.get_tier_for_count(count)

        #se o tier mudou, actualiza no Stripe - upgrade/downgrade automático
        tier_changed = new_tier != subscription.tier
        has_active_stripe_sub =(
            subscription.stripe_subscription_id is not None and 
            subscription.status == SubscriptionStatus.ACTIVE
        )

        if tier_changed and has_active_stripe_sub:
            new_price_id = TIER_CONFIG[new_tier]["price_id"]
            try:
                StripeService.update_subscription_price(subscription.stripe_subscription_id, new_price_id)
            except Exception:
                # Não bloqueia a operação se o Stripe falhar — o webhook irá sincronizar
                pass

        #Actualiza contagem e tier na BD
        subscription.active_clients_count = count
        subscription.tier = new_tier
        subscription.updated_at = datetime.now(timezone.utc)
        session.add(subscription)
        session.commit()
        session.refresh(subscription)

        return subscription
    
    @staticmethod
    def has_active_access(subscription: Optional[TrainerSubscription]) -> bool:
        """
        Verifica se o trainer tem acesso activo à plataforma.

        Retorna False se:
            - Não tem subscrição
            - Trial expirado
            - Subscrição cancelada
        """

        if not subscription:
            return False
        
        #Verifica se o status permite acesso
        if subscription.status not in SubscriptionStatus.ALLOWED:
            return False
        
        #se está em trial, verifica se o período de trial não expirou
        if subscription.status == SubscriptionStatus.TRIALING:
            if subscription.trial_end and date.today() > subscription.trial_end.date():
                return False
            
        return True
    
    @staticmethod
    def get_subscription(session: Session, trainer_user_id: str) -> Optional[TrainerSubscription]:
        """
        Busca a subscrição do trainer na BD.

        Retorna None se não existir.
        """
        return session.exec(
            select(TrainerSubscription).where(TrainerSubscription.trainer_user_id == trainer_user_id)
        ).first()
    
#----------------------------
# Função auxiliares privadas
#----------------------------

def _get_upgrade_message(current_tier: str) -> str:
    """
    Retorna uma mensagem de sugestão de upgrade com base no tier actual.

    Exemplo:
        "Para adicionar mais clientes, faça upgrade para o tier STARTER (20€/mês)."
    """
    if current_tier == SubscriptionTier.FREE:
        return "PRO (40€/mês) para clientes ilimitados."
    elif current_tier == SubscriptionTier.STARTER:
        return "PRO (40€/mês) para clientes ilimitados."
    else:
        return ""