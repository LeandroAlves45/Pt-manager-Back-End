"""
Router de administração — apenas superusers.

O superuser tem visibilidade global sobre toda a plataforma:
    - Ver todos os trainers e o estado das suas subscrições
    - Suspender/reactivar trainers
    - Ver métricas globais (total de trainers, clientes, receita estimada)
    - Gerir o catálogo global de exercícios e alimentos

Endpoints:
    GET  /admin/metrics              — métricas globais
    GET  /admin/trainers             — lista todos os trainers
    POST /admin/trainers/{id}/suspend  — suspende um trainer
    POST /admin/trainers/{id}/activate — reactiva um trainer
    POST /admin/trainers/{id}/grant-exemption    — concede isenção de billing
    POST /admin/trainers/{id}/revoke-exemption   — revoga isenção de billing
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel

from app.api.deps import db_session
from app.core.security import require_superuser
from app.db.models.user import User
from app.db.models.trainer_subscription import TrainerSubscription, SubscriptionStatus, SubscriptionTier
from app.db.models.client import Client
from app.services.subscription_service import TIER_CONFIG

router = APIRouter(prefix="/admin", tags=["Admin"])

#-------------------------------
# Schemas de resposta 
#-------------------------------

class TrainerSummary(BaseModel):
    #Resumo de um trainer para listagem no admin
    user_id: str
    full_name: str
    email: str
    is_active: bool
    is_exempt_from_billing: bool
    subscription_status: Optional[str]
    subscription_tier: Optional[str]
    active_clients_count: int
    montly_eur: int
    trial_end: Optional[datetime]
    joined_at: datetime

    model_config = {"from_attributes": True}

class PlatformMetrics(BaseModel):
    #Métricas globais da plataforma para o dashboard do superuser
    total_trainers: int
    active_trainers: int
    trialing_trainers: int
    total_clients: int
    estimated_monthly_revenue_eur: int


#-------------------------------
# Endpoints
#-------------------------------

@router.get("/metrics", response_model=PlatformMetrics)
async def get_metrics(
    session: Session = Depends(db_session),
    current_user = Depends(require_superuser)
) -> PlatformMetrics:
    
    # Devolve métricas globais da plataforma para o superuser

    # Total de trainers registados
    all_trainers = session.exec(select(User).where(User.role == "trainer")).all()
    total_trainers = len(all_trainers)

    # Subscrições
    all_subs = session.exec(select(TrainerSubscription)).all()

    # Um trainer está "ativo" se o status está dentro do conjunto de estados permitidos
    ALLOWED_STATUSES = {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING}

    active_trainers = sum(1 for subs in all_subs if subs.status in ALLOWED_STATUSES)
    trialing_trainers = sum(1 for subs in all_subs if subs.status == SubscriptionStatus.TRIALING)

    #Receita mensal estimada (soma dos tiers dos trainers que pagam)
    estimated_monthly_revenue_eur = sum(TIER_CONFIG[subs.tier]["monthly_eur"] for subs in all_subs if subs.status == SubscriptionStatus.ACTIVE)

    #Total de clientes na plataforma
    total_clients = len(session.exec(select(Client)).all())

    return PlatformMetrics(
        total_trainers=total_trainers,
        active_trainers=active_trainers,
        trialing_trainers=trialing_trainers,
        total_clients=total_clients,
        estimated_monthly_revenue_eur=estimated_monthly_revenue_eur,
    )

@router.get("/trainers", response_model=list[TrainerSummary])
async def list_trainers(
    status_filter: Optional[str] = None, #active, trialing, past_due, cancelled
    session: Session = Depends(db_session),
    current_user = Depends(require_superuser)
) -> list[TrainerSummary]:
    #Lista todos os trainers com o estado das suas subscrições. Permite filtrar por estado.

    trainers = session.exec(select(User).where(User.role == "trainer")).all()

    results = []
    for trainer in trainers:
        subs = session.exec(select(TrainerSubscription).where(TrainerSubscription.trainer_user_id == trainer.id)).first()

        #aplica filtro de status se fornecido
        if status_filter and subs and subs.status != status_filter:
            continue

        results.append(TrainerSummary(
            user_id=trainer.id,
            full_name=trainer.full_name,
            email=trainer.email,
            is_active=trainer.is_active,
            is_exempt_from_billing=getattr(trainer, "is_exempt_from_billing", False),
            subscription_status=subs.status if subs else None,
            subscription_tier=subs.tier if subs else None,
            active_clients_count=subs.active_clients_count if subs else 0,
            montly_eur=TIER_CONFIG[subs.tier]["monthly_eur"] if subs else 0,
            trial_end=subs.trial_end if subs else None,
            joined_at=trainer.created_at
        ))

    return results

@router.post("/trainers/{trainer_id}/suspend", status_code=status.HTTP_200_OK)
async def suspend_trainer(
    trainer_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(require_superuser)
) -> dict:
    
    # Suspende um trainer- bloqueia acesso imediatamente.

    trainer = session.get(User, trainer_id)
    if not trainer or trainer.role != "trainer":
        raise HTTPException(status_code=404, detail="Trainer não encontrado.")
    
    trainer.is_active = False
    trainer.updated_at = datetime.now(timezone.utc)
    session.add(trainer)
    session.commit()

    return {"detail": f"Trainer {trainer.full_name} suspenso."}

@router.post("/trainers/{trainer_id}/activate", status_code=status.HTTP_200_OK)
async def activate_trainer(
    trainer_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(require_superuser)
) -> dict:
    # Reativa um trainer suspenso.

    trainer = session.get(User, trainer_id)
    if not trainer or trainer.role != "trainer":
        raise HTTPException(status_code=404, detail="Trainer não encontrado.")
    
    trainer.is_active = True
    trainer.updated_at = datetime.now(timezone.utc)
    session.add(trainer)
    session.commit()

    return {"detail": f"Trainer {trainer.full_name} reativado."}

@router.post("/trainers/{trainer_id}/grant-exemption", status_code=status.HTTP_200_OK)
async def grant_exemption(
    trainer_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(require_superuser)
) -> dict:
    
    # Concede isenção de billing a um trainer (FREE forever).
    # Um trainer isento tem acesso equivalente á plataforma como o tier PRO, sem Stripe. 
    # Nunca pode ser auto-atribuída, apenas por um superuser.

    trainer = session.get(User, trainer_id)
    if not trainer or trainer.role != "trainer":
        raise HTTPException(status_code=404, detail="Trainer não encontrado.")
    
    trainer.is_exempt_from_billing = True
    trainer.updated_at = datetime.now(timezone.utc)
    session.add(trainer)
    session.commit()

    return {"detail": f"Isenção de billing concedida a {trainer.full_name}."}

@router.post("/trainers/{trainer_id}/revoke-exemption", status_code=status.HTTP_200_OK)
async def revoke_exemption(
    trainer_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(require_superuser)
) -> dict:
    
    # Revoga isenção de billing de um trainer, obrigando-o a subscrever para continuar a usar a plataforma.
    # Senão será bloqueado com HTTP 402

    trainer = session.get(User, trainer_id)
    if not trainer or trainer.role != "trainer":
        raise HTTPException(status_code=404, detail="Trainer não encontrado.")
    
    trainer.is_exempt_from_billing = False
    trainer.updated_at = datetime.now(timezone.utc)
    session.add(trainer)
    session.commit()

    return {"detail": f"Isenção de billing revogada de {trainer.full_name}."}