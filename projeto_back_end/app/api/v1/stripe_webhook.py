from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, HTTPException, Header
from sqlmodel import Session, select
import stripe

from app.api.deps import db_session
from app.core.config import settings
from app.db.models.trainer_subscription import TrainerSubscription, SubscriptionStatus
from app.services.stripe_service import StripeService

router = APIRouter(prefix="/stripe-webhook", tags=["Stripe Webhooks"])

@router.post("/webhook", status_code=200)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
    session: Session = Depends(db_session)
):
    
    #Recebe e processa eventos do Stripe

    #O Stripe espera sempre uma resposta 200 rápida
    #O header "Stripe-Signature" é usado para verificar a autenticidade do evento recebido

    #Lê o payload do corpo da requisição e tenta construir o evento usando a biblioteca Stripe, verificando a assinatura com o segredo configurado. Se a verificação falhar, retorna um erro 400.
    payload = await request.body()

    #Verifica a assinatura 
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Assinatura do webhook é inválida")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao processar o webhook: {str(e)}")

    #rota de eventos
    event_type = event["type"]
    event_data = event["data"]["object"]

    handlers = {
        "customer.subscription.updated": _handle_subscription_updated,
        "customer.subscription.deleted": _handle_subscription_deleted,
        "invoice.payment_succeeded": _handle_payment_succeeded,
        "invoice.payment_failed": _handle_payment_failed,
        "customer.subscription.trial_will_end": _handle_trial_will_end,
    }

    handler = handlers.get(event_type)
    if handler:
        await handler(event_data, session)

    #devolve sempre 200 - se o evento não tem handler, apenas ignora
    #O Stripe não re-tenta eventos com resposta 200
    return {"received": True}

#-------------------------------
#Handlers individuais para cada tipo de evento
#--------------------------------

async def _handle_subscription_updated(data: dict, session: Session):
    """
    Evento: customer.subscription.updated

    Disparado quando:
        - O trial termina e a subscrição muda de estado
        - O cliente actualiza o método de pagamento
        - Fazemos upgrade/downgrade de tier

    O campo data["status"] reflecte o estado actual no Stripe:
        trialing  → em trial
        active    → pago e em dia
        past_due  → pagamento falhou, em grace period
        cancelled → cancelado
    """

    stripe_subscription_id = data.get("id")
    stripe_status = data.get("status")
    current_period_end_ts = data.get("current_period_end")
    current_period_starts_at_ts = data.get("current_period_start")

    subscription = session.exec(
        select(TrainerSubscription)
        .where(TrainerSubscription.stripe_subscription_id == stripe_subscription_id)
    ).first()

    if not subscription:
        return #Subscrição não encontrada, ignora
    
    #Mapeia o status do Stripe para o nosso modelo
    status_map = {
        "trialing": SubscriptionStatus.TRIALING,
        "active": SubscriptionStatus.ACTIVE,
        "past_due": SubscriptionStatus.PAST_DUE,
        "cancelled": SubscriptionStatus.CANCELLED,
        "unpaid": SubscriptionStatus.CANCELLED,
        "incomplete": SubscriptionStatus.TRIAL_EXPIRED,
        "incomplete_expired": SubscriptionStatus.TRIAL_EXPIRED,
    }

    new_status = status_map.get(stripe_status, SubscriptionStatus.CANCELLED)
    subscription.status = new_status

    if current_period_starts_at_ts:
        subscription.current_period_start = datetime.fromtimestamp(current_period_starts_at_ts, tz=timezone.utc)

    if current_period_end_ts:
        subscription.current_period_end = datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)

    subscription.updated_at = datetime.now(timezone.utc)
    session.add(subscription)
    session.commit()

async def _handle_subscription_deleted(data: dict, session: Session):
    """
    Evento: customer.subscription.deleted

    Disparado quando:
        - O cliente cancela a subscrição
        - A subscrição é cancelada automaticamente por falta de pagamento (dependendo da configuração do Stripe)
    """

    stripe_subscription_id = data.get("id")

    subscription = session.exec(
        select(TrainerSubscription)
        .where(TrainerSubscription.stripe_subscription_id == stripe_subscription_id)
    ).first()

    if not subscription:
        return #Subscrição não encontrada, ignora
    
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.updated_at = datetime.now(timezone.utc)
    session.add(subscription)
    session.commit()

async def _handle_payment_succeeded(data: dict, session: Session):
    """
    Evento: invoice.payment_succeeded

    Disparado quando um pagamento de fatura é bem-sucedido. Pode ser usado para reativar uma subscrição que estava em past_due.
    """
    stripe_customer_id = data.get("customer")
    stripe_subscription_id = data.get("subscription")

    if not stripe_subscription_id:
        return #Sem subscrição associada, ignora

    subscription = session.exec(
        select(TrainerSubscription)
        .where(TrainerSubscription.stripe_subscription_id == stripe_subscription_id)
    ).first()

    if not subscription:
        return #Subscrição não encontrada, ignora
    
    subscription.status == SubscriptionStatus.ACTIVE
    subscription.updated_at = datetime.now(timezone.utc)
    session.add(subscription)
    session.commit()

async def _handle_payment_failed(data: dict, session: Session):
    """
    Evento: invoice.payment_failed

    Disparado quando um pagamento de fatura falha. Pode ser usado para colocar a subscrição em past_due.
    """
    
    stripe_subscription_id = data.get("subscription")

    if not stripe_subscription_id:
        return #Sem subscrição associada, ignora

    subscription = session.exec(
        select(TrainerSubscription)
        .where(TrainerSubscription.stripe_subscription_id == stripe_subscription_id)
    ).first()

    if not subscription:
        return #Subscrição não encontrada, ignora
    
    subscription.status == SubscriptionStatus.PAST_DUE
    subscription.updated_at = datetime.now(timezone.utc)
    session.add(subscription)
    session.commit()

async def _handle_trial_will_end(data: dict, session: Session):
    """
    Evento: customer.subscription.trial_will_end

    Disparado 3 dias antes do final do trial. Pode ser usado para enviar notificações ou e-mails de lembrete.
    """

    # TODO: Implementar lógica de notificação para lembrar o cliente que o trial está prestes a terminar. Isso pode incluir enviar um e-mail ou uma notificação in-app.
    pass