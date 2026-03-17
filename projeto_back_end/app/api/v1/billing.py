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
from app.db.models.trainer_subscription import SubscriptionTier
from app.services.stripe_service import StripeService
from app.schemas.subscription import SubscriptionRead
from app.services.subscription_service import SubscriptionService, TIER_CONFIG

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
        active_clients_count=subscription.active_clients_count,
        max_clients=tier_config["max_clients"],
        trial_end=subscription.trial_end,
        current_period_end=subscription.current_period_end,
        can_add_client=can_add,
        upgrade_message=upgrade_msg,
    )

@router.post("/checkout", status_code=status.HTTP_200_OK)
async def create_checkout_session(
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer) #trainer com ou sem subscrição ativa
) -> dict:
    # Gera URL do Stripe Checkout para o trainer configurar o método de pagamento e iniciar subscrição
    # O Stripe redireciona para success_url ou cancel_url após o processo

    subscription = SubscriptionService.get_subscription(session, current_user.id)

    if not subscription or not subscription.stripe_customer_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscrição não encontrada.")
    
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

@router.post("/portal", status_code=status.HTTP_200_OK)
async def create_billing_portal(
    session: Session = Depends(db_session),
    current_user = Depends(require_trainer) #trainer com ou sem subscrição ativa
) -> dict:
    # Gera URL do Stripe Billing Portal para o trainer gerir a subscrição
    # O Billing Portal permite ao trainer atualizar o método de pagamento, cancelar a subscrição, etc.

    subscription = SubscriptionService.get_subscription(session, current_user.id)

    if not subscription or not subscription.stripe_customer_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscrição não encontrada.")
    
    try:
        portal_url = StripeService.create_billing_portal_session(
            stripe_customer_id=subscription.stripe_customer_id,
            return_url=settings.stripe_portal_url,
        )
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Erro ao criar sessão do portal de faturação.") from e
    
    return {"portal_url": portal_url}