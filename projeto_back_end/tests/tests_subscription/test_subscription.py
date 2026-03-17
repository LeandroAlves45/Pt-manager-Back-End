"""
Testes unitários para o SubscriptionService.

Estes testes cobrem a lógica pura de negócio:
    - Cálculo de tiers
    - Verificação de limites de clientes
    - Verificação de acesso activo

São testes unitários puros — não tocam na BD nem no Stripe.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone

from app.services.subscription_service import SubscriptionService
from app.db.models.trainer_subscription import SubscriptionStatus, SubscriptionTier

def _make_subscription(
    status=SubscriptionStatus.ACTIVE,
    tier=SubscriptionTier.STARTER,
    active_clients_count=0,
    trial_end=None,
) -> MagicMock:
    """
    Factory que cria um objecto mock de TrainerSubscription.
    Usar MagicMock em vez de instanciar o modelo SQLModel evita precisar de BD.
    """

    sub = MagicMock()
    sub.status = status
    sub.tier = tier
    sub.active_clients_count = active_clients_count
    sub.trial_end = trial_end
    
    return sub

#-------------------------------
# Testes de get_tier_for_count
#-------------------------------

class TestGetTierForCount:
    #Testa o calculo de tier com base no numero de clientes activos

    def test_zero_clients_is_free(self):
        assert SubscriptionService.get_tier_for_count(0) == SubscriptionTier.FREE

    def test_five_clients_is_free(self):
        assert SubscriptionService.get_tier_for_count(5) == SubscriptionTier.FREE

    def test_six_clients_is_starter(self):
        assert SubscriptionService.get_tier_for_count(6) == SubscriptionTier.STARTER

    def test_forty_nine_clients_is_starter(self):
        assert SubscriptionService.get_tier_for_count(49) == SubscriptionTier.STARTER

    def test_fifty_clients_is_pro(self):
        assert SubscriptionService.get_tier_for_count(50) == SubscriptionTier.PRO

    def test_hundred_clients_is_pro(self):
        assert SubscriptionService.get_tier_for_count(100) == SubscriptionTier.PRO

    def test_boundary_between_free_and_starter(self):
        assert SubscriptionService.get_tier_for_count(5) == SubscriptionTier.FREE
        assert SubscriptionService.get_tier_for_count(6) == SubscriptionTier.STARTER

    def test_boundary_between_starter_and_pro(self):
        assert SubscriptionService.get_tier_for_count(49) == SubscriptionTier.STARTER
        assert SubscriptionService.get_tier_for_count(50) == SubscriptionTier.PRO

#-------------------------------
# Testes de can_add_client
#-------------------------------

class TestCanAddClient:
    #Testa as regras de quando um trainer pode adicionar mais clientes

    def test_free_tier_below_limit_can_add(self):
        #Free com 3 clientes activos pode adicionar mais (limite 5)
        sub = _make_subscription(
            status=SubscriptionStatus.ACTIVE,
            tier=SubscriptionTier.FREE,
            active_clients_count=3
        )

        can_add, msg = SubscriptionService.can_add_client(sub)
        assert can_add is True
        assert msg == "" #Não deve haver mensagem de erro

    def test_free_tier_at_limit_cannot_add(self):
        #Free com 5 clientes activos Não pode adicionar mais (limite 5)
        sub = _make_subscription(
            status=SubscriptionStatus.ACTIVE,
            tier=SubscriptionTier.FREE,
            active_clients_count=5
        )
        can_add, msg = SubscriptionService.can_add_client(sub)
        assert can_add is False
        assert len(msg) > 0 #Deve haver mensagem explicando que não pode adicionar
        assert "FREE" in msg #Mensagem deve mencionar que o limite do tier FREE é 5 clientes    

    def test_starter_tier_at_limit_cannot_add(self):
        #starter com 49 clientes Não pode adicionar mais (limite 49)
        sub = _make_subscription(
            status=SubscriptionStatus.ACTIVE,
            tier=SubscriptionTier.STARTER,
            active_clients_count=49
        )
        can_add, msg = SubscriptionService.can_add_client(sub)
        assert can_add is False
        assert "pro" in msg.lower() #Deve haver mensagem explicando que não pode adicionar

    def test_pro_tier_no_limit(self):
        #PRO sem limite
        sub = _make_subscription(
            status=SubscriptionStatus.ACTIVE,
            tier=SubscriptionTier.PRO,
            active_clients_count=999
        )
        can_add, msg = SubscriptionService.can_add_client(sub)
        assert can_add is True

    def test_cancelled_subscription_cannot_add(self):
        #Subscrição cancelada não pode adicionar clientes
        sub = _make_subscription(
            status=SubscriptionStatus.CANCELLED,
            tier=SubscriptionTier.STARTER,
            active_clients_count=0
        )
        can_add, msg = SubscriptionService.can_add_client(sub)
        assert can_add is False
        assert len(msg) > 0 #Deve haver mensagem explicando que não pode adicionar

    def test_trial_expired_cannot_add(self):
        #Subscrição em trial expirado não pode adicionar clientes
        sub = _make_subscription(
            status=SubscriptionStatus.TRIAL_EXPIRED,
            tier=SubscriptionTier.FREE,
            active_clients_count=0,
        )

        can_add, msg = SubscriptionService.can_add_client(sub)
        assert can_add is False
        assert "trial" in msg.lower() #Mensagem deve mencionar que o trial expirou

    def test_trialling_within_limits_can_add(self):
        #Subscrição em trial dentro dos limites pode adicionar clientes
        sub = _make_subscription(
            status=SubscriptionStatus.TRIALING,
            tier=SubscriptionTier.FREE,
            active_clients_count=2,
        )

        can_add, msg = SubscriptionService.can_add_client(sub)
        assert can_add is True
        assert "trial" in msg.lower() #Mensagem deve mencionar que está em trial

    def test_past_due_within_limit_can_add(self):
        #Subscrição em past_due dentro dos limites pode adicionar clientes (ainda está em grace period)
        sub = _make_subscription(
            status=SubscriptionStatus.PAST_DUE,
            tier=SubscriptionTier.STARTER,
            active_clients_count=10,
        )

        can_add, msg = SubscriptionService.can_add_client(sub)
        assert can_add is True
        assert "pagamento" in msg.lower() #Mensagem deve mencionar que o pagamento falhou, mas ainda pode adicionar durante o grace period

#-------------------------------
# Testes de has_active_acess
#-------------------------------

class TestHasActiveAccess:
    #Testa a verificação de acesso activo á plataforma

    def test_none_subscription_has_no_access(self):
        #Sem subscrição, sem acesso
        assert SubscriptionService.has_active_access(None) is False

    def test_active_subscription_has_access(self):
        #Subscrição activa tem acesso
        sub = _make_subscription(status=SubscriptionStatus.ACTIVE)
        assert SubscriptionService.has_active_access(sub) is True
    
    def test_trialing_subscription_has_access(self):
        #Subscrição em trial tem acesso
        future = datetime.now(timezone.utc) + timedelta(days=10)
        sub = _make_subscription(status=SubscriptionStatus.TRIALING, trial_end=future)
        assert SubscriptionService.has_active_access(sub) is True

    def test_trialing_past_end_has_no_access(self):
        #Subscrição em trial expirado não tem acesso
        past = datetime.now(timezone.utc) - timedelta(days=1)
        sub = _make_subscription(status=SubscriptionStatus.TRIALING, trial_end=past)
        assert SubscriptionService.has_active_access(sub) is False

    def test_cancelled_subscription_has_no_access(self):
        #Subscrição cancelada não tem acesso
        sub = _make_subscription(status=SubscriptionStatus.CANCELLED)
        assert SubscriptionService.has_active_access(sub) is False
    
    def test_past_due_has_access(self):
        #Subscrição em past_due ainda tem acesso (durante grace period)
        sub = _make_subscription(status=SubscriptionStatus.PAST_DUE)
        assert SubscriptionService.has_active_access(sub) is True