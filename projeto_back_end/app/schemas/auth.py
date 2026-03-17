"""
Schemas Pydantic para o módulo de autenticação.

Separação de responsabilidades:
- UserCreate  : dados para criar um novo utilizador (recebido da API)
- UserRead    : dados do utilizador devolvidos pela API (nunca inclui password)
- UserUpdate  : campos que podem ser atualizados
- TokenOut    : resposta do endpoint de login (o token JWT)
- LoginIn     : credenciais enviadas no login
"""

from typing import Optional, Literal
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

class LoginIn(BaseModel):
    """
    Credenciais para login. Enviadas pelo cliente no pedido de autenticação.
    """

    email: EmailStr 
    password: str = Field(min_length=6)

class TokenOut(BaseModel):
    """
    Resposta do endpoint de login.

    access_token : o JWT que o cliente deve guardar e enviar nos requests seguintes
    token_type   : sempre "bearer" — é o standard HTTP para este tipo de token
    role         : incluído por conveniência para o frontend redirecionar para o dashboard correto
    """

    access_token: str
    token_type: str = "bearer"
    role: str # "trainer" ou "client"
    user_id: str
    full_name: str

class UserCreate(BaseModel):
    """
    Payload para criar um novo utilizador.

    Apenas trainers podem criar utilizadores (via endpoint protegido).
    O campo `password` é recebido em plain text e convertido para hash no handler.
    """

    email: EmailStr
    password: str = Field(min_length=6, description="Password com pelo menos 6 caracteres")
    full_name: str = Field(min_length=2)

    #se role = "client", deve ser fornecido o client_id para ligar ao registo de cliente
    #se role = "trainer", este campo é ignorado
    role: Literal["trainer", "client"] = "client"
    client_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_client_id_for_client_role(self) -> "UserCreate":
        """
        Validação de negócio: se o role é "client", o client_id é obrigatório.
        Desta forma garantimos que cada conta de cliente está sempre ligada a um registo.
        """

        if self.role == "client" and not self.client_id:
            raise ValueError("O campo client_id é obrigatório para utilizadores com role 'client'")
        return self
    
class UserRead(BaseModel):
    """
    Dados do utilizador devolvidos pela API.

    Nunca inclui a password ou outros campos sensíveis.
    """

    id: str
    email: EmailStr
    full_name: str
    role: str
    client_id: Optional[str] #apenas para role "client"
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = { "from_attributes": True }

class UserUpdate(BaseModel):
    """
    Campos que podem ser atualizados num utilizador.

    Todos os campos são opcionais, permitindo updates parciais.
    """

    full_name: Optional[str] = Field(None, min_length=2)
    is_active: Optional[bool]

class ChangePassword(BaseModel):
    """
    Payload para endpoint de mudança de password.

    O utilizador deve fornecer a password atual para confirmar a identidade,
    e a nova password deve cumprir os requisitos mínimos.
    """

    current_password: str 
    new_password: str = Field(..., min_length=6)