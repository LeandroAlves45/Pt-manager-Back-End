"""
Endpoint de self-signup para trainers.

Este é o único endpoint público (além de /auth/login e /health).
Não requer token — é o ponto de entrada de novos trainers na plataforma.

Fluxo completo:
    1. Recebe email + password + full_name
    2. Valida unicidade do email
    3. Cria User (role="trainer") na BD
    4. Cria Customer no Stripe
    5. Cria Subscription em trial no Stripe
    6. Cria TrainerSubscription na BD
    7. Gera JWT e devolve ao frontend
    8. Frontend vai usar o checkout_url para o trainer adicionar cartão (opcional durante trial)
"""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, status
from sqlmodel import Session, select

from app.api.deps import db_session
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.models.user import User
from app.db.models.trainer_subscription import TrainerSubscription, SubscriptionStatus, SubscriptionTier
from app.schemas.subscription import TrainerSignupIn, TrainerSignupOut
from app.services.stripe_service import StripeService

router = APIRouter(prefix="/signup", tags=["Signup"])

@router.post("/trainer", response_model=TrainerSignupOut, status_code=status.HTTP_201_CREATED)
async def trainer_signup(
    payload: TrainerSignupIn,
    session: Session = Depends(db_session)
):
    #Registo público de um novo trainer
    #Após o signup, o trainer recebe:
    # - Um JWT para autenticação imediata
    # - Um checkout_url para configurar o método de pagamento (opcional durante trial)
    # - Trial de 15 dias gratuito

    email_str = str(payload.email)


    #Verificamos se o email já existe
    existing = session.exec(select(User).where(User.email == email_str)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email já registado.")
    
    #Criamos o User na BD
    user = User(
        email=email_str,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role="trainer",
    )
    session.add(user)

    try:
        #commit do user primeiro
        session.commit()
        session.refresh(user)
    
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao criar usuário: {str(e)}")
    
    #integração com Stripe

    stripe_customer_id = None
    stripe_subscription_id = None
    trial_end_dt = None
    checkout_url = None

    try:
        #Criar o Customer no Stripe
        stripe_customer_id = StripeService.create_customer(
            email=email_str,
            full_name=payload.full_name,
            trainer_user_id=user.id
        )

        #Cria a subscrição em trial
        stripe_sub = StripeService.create_trial_subscription(
            stripe_customer_id=stripe_customer_id,
            trial_days= settings.trial_days,
        )
        stripe_subscription_id = stripe_sub.id

        #Converte o trial_end do Stripe (Unix timestamp) para datetime
        if stripe_sub.trial_end:
            trial_end_dt = datetime.fromtimestamp(stripe_sub.trial_end, tz=timezone.utc)

        #Gerar o checkout_url para o cliente configurar o método de pagamento
        if stripe_subscription_id and stripe_customer_id:
            try:
                checkout_url = StripeService.create_checkout_session(
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    success_url=settings.stripe_success_url,
                    cancel_url=settings.stripe_cancel_url,
                )
            except Exception:
                #Se falhar a criação do checkout, não é crítico — o trainer pode configurar o pagamento depois
                checkout_url = None
    except Exception as e:
        #Se falhar a integração com Stripe, devemos limpar o user criado para evitar inconsistências
        try:
            session.delete(user)
            session.commit()
        except Exception:
            pass #Se falhar a limpeza, não há muito o que fazer — o user ficará órfão, mas é melhor do que ter um user sem subscrição
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, 
                            detail=f"Erro ao configurar a subscrição. Tenta novamente mais tarde") from e
    #Cria a linha de subscrição na BD local
    subcription=TrainerSubscription(
        trainer_user_id=user.id,
        status=SubscriptionStatus.TRIALING,
        tier=SubscriptionTier.FREE,
        trial_end=trial_end_dt,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        active_clients_count=0,
    )
    session.add(subcription)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao guardar subscrição.") from e
    
    #Gerar JWT para o trainer
    token= create_access_token(subject=user.id, role="trainer", full_name=user.full_name)

    return TrainerSignupOut(
        access_token=token,
        user_id=user.id,
        full_name=user.full_name,
        checkout_url=checkout_url,
        trial_end=trial_end_dt,
        message= (
            f"Bem-vindo/a, {user.full_name}!"
            f"Tens {settings.trial_days} dias de trial gratuito."
            "Adiciona um método de pagamento para não perder o acesso após o trial."
        ),
    )