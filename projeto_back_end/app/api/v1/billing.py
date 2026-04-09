"""
Router de billing — dashboard de subscrição do trainer.

Endpoints:
    GET  /billing/subscription      — estado actual da subscrição
    POST /billing/checkout          — gera URL do Stripe Checkout (adicionar cartão)
    POST /billing/portal            — gera URL do Billing Portal (gerir subscrição)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import db_session
from app.core.config import settings
from app.core.security import require_trainer
from app.db.models.trainer_subscription import SubscriptionTier, SubscriptionStatus
from app.services.stripe_service import StripeService
from app.schemas.subscription import SubscriptionRead
from app.services.subscription_service import SubscriptionService, TIER_CONFIG
from app.core.db_errors import commit_or_rollback

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])

# Labels legíveis para os tiers
TIER_LABELS = {
    SubscriptionTier.FREE: "Free",
    SubscriptionTier.STARTER: "Starter",
    SubscriptionTier.PRO: "Pro",
}

#-------------------------------
# Endpoints
#-------------------------------

# =============================================================================
# GET /subscription — estado actual da subscrição
# =============================================================================

@router.get("/subscription", response_model=SubscriptionRead)
async def get_subscription(
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer) #trainer com ou sem subscrição ativa
) -> SubscriptionRead:
    # Devolve o estado atual da subscrição do trainer
    # Inclui: status, tier, contagem de clientes, limitesdo tier, trail_end, e se o trainer pode adicionar mais clientes

    subscription = SubscriptionService.get_subscription(session, current_user.id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscrição não encontrada.")
    
    tier_config = TIER_CONFIG[subscription.tier]
    can_add, upgrade_msg = SubscriptionService.can_add_client(subscription)

    return SubscriptionRead(
        status=subscription.status,
        tier=subscription.tier,
        tier_label=TIER_LABELS.get(subscription.tier, subscription.tier),
        monthly_eur=tier_config["monthly_eur"],
        max_clients=tier_config["max_clients"],
        active_clients_count=subscription.active_clients_count,
        trial_end=subscription.trial_end,
        current_period_end=subscription.current_period_end,
        can_add_client=can_add,
        upgrade_message=upgrade_msg,
    )

# =============================================================================
# POST /checkout — gera URL do Stripe Checkout
# =============================================================================

@router.post("/checkout", status_code=status.HTTP_200_OK)
async def create_checkout_session(
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer) #trainer com ou sem subscrição ativa
) -> dict:
    # Gera URL do Stripe Checkout para o trainer configurar o método de pagamento e iniciar subscrição
    # O Stripe redireciona para success_url ou cancel_url após o processo

    subscription = SubscriptionService.get_subscription(session, current_user.id)

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscrição não encontrada.")
    
    # Verifica se o Stripe está configurado neste ambiente
    stripe_configured = bool(
        settings.stripe_secret_key and
        settings.stripe_price_free and
        settings.stripe_price_free != ""
    )
    
    if not stripe_configured:
        raise HTTPException(
            status_code=400,
            detail=(
                "Stripe não está configurado neste ambiente. "
                "Configura STRIPE_SECRET_KEY e STRIPE_PRICE_FREE nas variáveis de ambiente."
            ),
        )
    
    if not subscription.stripe_customer_id:
        try: 
            logger.info(
                f"[BILLING] Trainer {current_user.email} não tem stripe_customer_id. "
                "A registar no Stripe agora."
            )

            # Criar Costumer no Stripe
            stripe_customer_id = StripeService.create_customer(
                email=current_user.email,
                full_name=current_user.full_name,
                trainer_user_id=current_user.id,
            )

            # Criar Subscription em trial no Stripe
            trial_days = 1
            if subscription.trial_end:
                remaining = (subscription.trial_end - datetime.now(timezone.utc)).days
                trial_days = max(1, remaining)

            stripe_sub = StripeService.create_trial_subscription(
                stripe_customer_id=stripe_customer_id,
                trial_days=trial_days,
            )

            # Atualizar subscrição com stripe_customer_id e stripe_subscription_id
            subscription.stripe_customer_id = stripe_customer_id
            subscription.stripe_subscription_id = stripe_sub.id
            session.add(subscription)
            commit_or_rollback(session)

            logger.info(f"[BILLING] Trainer {current_user.email} registado no Stripe com sucesso.")
        
        except Exception as e:
            logger.error(f"[BILLING] Erro ao registar trainer no Stripe: {e}")
            raise HTTPException(
                status_code=502,
                detail="Erro ao criar conta no Stripe. Verifica as credenciais Stripe nas variáveis de ambiente.",
            ) from e
    
    # Gera o Url do checkout
    try:
        checkout_url = StripeService.create_checkout_session(
            stripe_customer_id=subscription.stripe_customer_id,
            stripe_subscription_id=subscription.stripe_subscription_id or "",
            success_url=settings.stripe_success_url,
            cancel_url=settings.stripe_cancel_url,
        )
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Erro ao criar sessão de checkout.") from e
    
    return {"checkout_url": checkout_url}


# =============================================================================
# POST /portal — gera URL do Stripe Billing Portal
# =============================================================================

@router.post("/portal", status_code=status.HTTP_200_OK)
async def create_billing_portal(
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer) #trainer com ou sem subscrição ativa
) -> dict:
    # Gera URL do Stripe Billing Portal para o trainer gerir a subscrição
    # O Billing Portal permite ao trainer atualizar o método de pagamento, cancelar a subscrição, etc.

    subscription = SubscriptionService.get_subscription(session, current_user.id)

    if not subscription or not subscription.stripe_customer_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=(
                "Ainda não tens uma conta Stripe configurada. "
                "Usa a opção 'Adicionar método de pagamento' primeiro."
            ),
)
    
    try:
        portal_url = StripeService.create_billing_portal_session(
            stripe_customer_id=subscription.stripe_customer_id,
            return_url=settings.stripe_portal_url,
        )
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Erro ao criar sessão do portal de faturação.") from e
    
    return {"portal_url": portal_url}