"""
Serviço de integração com o Stripe.

Este módulo é a única camada da aplicação que fala directamente com a API do Stripe.
Todos os outros módulos que precisem de operações Stripe chamam este serviço.

Vantagens desta separação:
    - Facilita testes (podes fazer mock deste serviço)
    - Centraliza a lógica de erro do Stripe
    - Se mudares de provider de pagamentos, só alteras aqui

Fluxo completo de um novo trainer:
    1. signup               → create_customer()
    2. criar subscrição     → create_trial_subscription()
    3. adicionar cartão     → create_checkout_session() → redireciona para Stripe
    4. upgrade de tier      → update_subscription_price()
    5. cancelar             → cancel_subscription()
    6. ver facturas         → create_billing_portal_session()
"""

import stripe
from app.core.config import settings
from typing import Optional

#Configura a chave secreta da API Stripe
stripe.api_key = settings.stripe_secret_key

class StripeService:
    """
    Wrapper em torno da API do Stripe.
    """

    @staticmethod
    def create_customer(email: str, full_name: str, trainer_user_id) -> str:
        """
        Cria um Customer no Stripe para o trainer.

        O Customer é criado no momento do registo, mesmo antes de qualquer pagamento.
        Isto permite-nos:
            - Enviar emails do Stripe (recibos, falhas de pagamento)
            - Ligar a subscrição ao customer mais tarde
            - Ver o trainer no dashboard do Stripe desde o início

        metadata: campos adicionais que o Stripe guarda — úteis para reconciliação.

        Retorna: stripe_customer_id (ex: "cus_Abc123XYZ")
        """
        customer = stripe.Customer.create(
            email=email,
            name=full_name,
            metadata={"trainer_user_id": trainer_user_id}
        )
        return customer.id
    
    @staticmethod
    def create_trial_subscription(stripe_customer_id: str, trial_days: int = 15) -> stripe.Subscription:
        """
        Cria uma subscrição em modo trial para o trainer.

        Durante o trial:
            - Não é cobrado nada
            - trial_end define quando o trial acaba
            - payment_behavior="default_incomplete" → não exige cartão imediatamente
            - Quando o trial acabar, o Stripe muda para o Price do tier FREE (0€)

        Se o trainer não adicionar cartão antes de trial_end:
            - O Stripe envia evento "customer.subscription.trial_will_end" (3 dias antes)
            - Após trial_end, enviamos evento "customer.subscription.updated" com status="past_due"
            - O nosso webhook apanha isto e marca o trainer como trial_expired

        Retorna: objecto Subscription do Stripe (com .id, .status, .trial_end, etc.)
        """
        subscription = stripe.Subscription.create(
            customer=stripe_customer_id,
            items=[{"price": settings.stripe_price_free}], #Começa no tier FREE durante o trial
            trial_period_days=trial_days,
            #Default_incomplete: náo requer pagamento imediato
            payment_behavior="default_incomplete",
            #expand=["latest_invoice.payment_intent"] permite obter o client_secret
            expand=["latest_invoice.payment_intent"] #Expande o payment_intent para obter detalhes do pagamento
        )
        return subscription.id

    @staticmethod
    def create_checkout_session(
        stripe_customer_id: str, 
        stripe_subscription_id:str,
        success_url: str,
        cancel_url: str
    ) -> str:
        """
        Cria uma sessão de checkout para o trainer.

        Retorna: URL da sessão de checkout
        """
        session = stripe.checkout.Session.create(
            customer=stripe_customer_id,
            mode="setup",
            currency="eur",
            setup_intent_data={
                "metadata": {
                    "stripe_subscription_id": stripe_subscription_id
                }
            },
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return session.url
    
    @staticmethod
    def update_subscription_price(stripe_subscription_id: str, new_price_id: str) -> stripe.Subscription:
        """
        Actualiza o tier de uma subscrição (ex: FREE → STARTER quando passa de 5 clientes).

        proration_behavior="always_invoice":
            - O Stripe calcula a diferença entre o preço antigo e o novo
            - Cria uma factura imediata pelo valor proporcional ao tempo restante
            - Ex: se muda a meio do mês, cobra metade da diferença

        Isto é chamado pela SubscriptionService quando o nº de clientes muda de tier.
        """
        #Busca a subscrição actual para obter o ID do item da subscrição
        subscription = stripe.Subscription.retrieve(stripe_subscription_id)
        item_id = subscription["items"]["data"][0]["id"]

        #Actualiza o item da subscrição para o novo price_id
        updated = stripe.Subscription.modify(
            stripe_subscription_id,
            items=[{
                "id": item_id,
                "price": new_price_id,
            }],
            proration_behavior="always_invoice"
        )
        return updated
    
    @staticmethod
    def cancel_subscription(stripe_subscription_id: str) -> stripe.Subscription:
        """
        Cancela uma subscrição.

        O Stripe mantém a subscrição activa até ao final do período pago.
        Ex: se o trainer cancelar a meio do mês, mantém acesso até ao final do mês.
        """
        return stripe.Subscription.delete(stripe_subscription_id)
    
    @staticmethod
    def create_billing_portal_session(stripe_customer_id: str, return_url: str) -> str:
        """
        Cria uma sessão para o portal de billing do Stripe.

        O portal de billing é onde o trainer pode:
            - Ver e pagar facturas
            - Actualizar os dados de pagamento
            - Cancelar a subscrição

        Retorna: URL do portal de billing
        """
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return session.url
    
    @staticmethod
    def construct_webhook_event(payload: bytes, sig_header: str) -> Optional[stripe.Event]:
        """
        Verifica a assinatura do webhook e constrói o evento do Stripe.

        Retorna o objeto Event se a assinatura for válida, ou None se for inválida.
        """
        return stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.stripe_webhook_secret
        )
