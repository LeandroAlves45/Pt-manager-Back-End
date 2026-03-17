from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr

class TrainerSignupIn(BaseModel):
    """
    Esquema para registo de um novo trainer.
    """
    email: EmailStr 
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2)


class TrainerSignupOut(BaseModel):
    """ Resposta após registo de um novo trainer. """

    access_token: str
    token_type: str = "bearer"
    user_id: str
    full_name: str
    # URL do Stripe Checkout para o trainer adicionar método de pagamento
    # None durante o trial — pode adicionar mais tarde
    checkout_url: Optional[str] = None
    trial_end: Optional[datetime] = None
    message: str

class SubscriptionRead(BaseModel):
    """
    Esquema para leitura da subscrição do trainer.
    Inclui informações relevantes para o frontend mostrar o estado da subscrição e sugerir ações (ex: upgrade).
    """
    status: str # trialing, active, cancelled, past_due, etc.
    tier: str # free, starter, pro
    tier_label: str # Rótulo legível do tier, ex: "FREE (0-5 clientes)", "STARTER (6-49 clientes)", "PRO (50+ clientes)"
    monthly_eur: int #Preço mensal do tier em euros, ex: 0, 20, 40
    max_clients: Optional[int] #Limite de clientes activos para o tier (None = sem limite)
    trial_end: Optional[datetime] = None
    current_period_end: Optional[datetime]
    can_add_client: bool #Se o trainer pode adicionar mais um cliente com base no estado da subscrição e número de clientes activos
    upgrade_message: str 

    model_config = {"from_attributes": True}