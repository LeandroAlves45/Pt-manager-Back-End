"""
Módulo de segurança — autenticação, autorização e guards de acesso.
 
Camadas de segurança por ordem de execução em cada pedido:
    1. require_api_key          — valida o header X-API-Key (aplica-se a todos os routers)
    2. get_current_user         — valida o JWT Bearer e devolve o utilizador da DB
    3. require_trainer /        — verifica o role do utilizador
       require_superuser /
       require_client
    4. require_active_subscription — verifica se o trainer tem subscrição activa
 
Dependencies disponíveis:
    get_current_user            — qualquer utilizador autenticado
    require_superuser           — apenas superusers
    require_trainer             — trainers e superusers (sem verificação de subscrição)
    require_active_subscription — trainers com subscrição activa (ou isentos de billing)
    require_client              — apenas clientes
    require_api_key             — validação da API key (aplicada globalmente)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Header, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from app.core.config import settings
from app.api.deps import db_session

#--------------------------------------------
# Hash de passwords - bcrypt via passlib
#--------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain_password: str) -> str:
    #Converte a password em hash usando bcrypt
    return pwd_context.hash(plain_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    #Verifica se a password em texto plano corresponde ao hash armazenado
    return pwd_context.verify(plain_password, hashed_password)

#--------------------------------------------
# JWT
#--------------------------------------------

bearer_scheme = HTTPBearer()
ALGORITHM = "HS256"

def create_access_token(
        subject: str, 
        role: str, 
        full_name: str, 
        client_id: str = None, 
        expires_delta: Optional[timedelta] = None,
) -> str:
    """Cria um token JWT com as claims necessárias para autenticação e controlo de acesso.

        Claims incluídas no payload:
        sub       — user ID (subject padrão JWT)
        role      — "superuser" | "trainer" | "client"
        full_name — nome completo para exibição no frontend sem pedido extra à API
        exp       — timestamp de expiração
        cid       — client_id (apenas para role="client", para o portal do cliente)
    """

    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = { 
        "sub": subject, 
        "role": role,
        "full_name": full_name,
        "exp": expire }
    
    # Inclui client_id apenas para clientes — evita payload desnecessariamente grande 
    if client_id is not None:
        payload["cid"] = client_id

    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)

#--------------------------------------------
# Dependencies de segurança
#--------------------------------------------

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), session: Session = Depends(db_session)):
    token = credentials.credentials
    """
    Valida o JWT Bearer token e devolve o utilizador autenticado da base de dados.
 
    Processo:
        1. Decodifica e valida o JWT (assinatura, expiração)
        2. Extrai o user_id do campo "sub"
        3. Busca o utilizador na DB para garantir que ainda existe e está activo
        4. Devolve o objecto User completo para uso nos handlers
 
    Lança HTTP 401 se:
        - O token for inválido ou expirado
        - O utilizador não existir na DB
        - A conta estiver inactiva (is_active=False)
    """

    from app.db.models.user import User
    from app.db.models.active_token import ActiveToken

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de autenticação inválido ou expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Verifica se o token está activo na tabela active_tokens — logout remove o token daqui, invalidando-o imediatamente
    active_token = session.exec(
        select(ActiveToken)
        .where(ActiveToken.user_id == user_id)
        .where(ActiveToken.token == token)
    ).first()

    if not active_token:
        raise credentials_exception
    
    # Busca o utilizador na DB para garantir que ainda existe e está activo
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception
    
    return user

# --------------------------------------------
# Dependencias de autorização por role
# --------------------------------------------

async def require_superuser(current_user = Depends(get_current_user)):
    """
    Garante que o utilizador autenticado é um superuser.
    Usado exclusivamente nas rotas /admin/*.
    Lança HTTP 403 se o role não for "superuser".
    """

    if current_user.role != "superuser":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: requer privilégios de superuser.",
        )
    return current_user

async def require_trainer(current_user = Depends(get_current_user)):
    """
    Garante que o utilizador é um trainer ou superuser.
 
    NÃO verifica subscrição — usar em rotas que devem funcionar
    mesmo sem subscrição activa (ex: billing, portal de pagamento).
    Superusers passam sempre — têm acesso a tudo.
    """

    if current_user.role not in {"trainer", "superuser"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a Personal Trainers.",
        )
    return current_user

async def require_active_subscription(current_user = Depends(require_trainer), session: Session = Depends(db_session)):
    """
    Dependency crítica para rotas operacionais do trainer.

    Verifica em cascata (ordem de verificação importa para performance):
        1. É superuser? → passa sempre (acesso global sem restrições)
        2. É trainer isento de billing? → passa sempre (free-forever trainer)
        3. Tem subscrição activa (trial válido ou paid activo)? → passa
        4. Caso contrário → HTTP 402 Payment Required

    Lança 402 Payment Required se a subscrição não estiver activa —
    o 402 é semanticamente correcto: "tens de pagar para aceder a este recurso".
    """

    # Camada 1: superusers têm acesso total, sem restrições de subscrição
    if current_user.role == "superuser":
        return current_user
    
    # Camada 2: trainer isento de billing tem acesso total, sem necessidade de subscrição
    if getattr(current_user, "is_exempt_from_billing", False):
        return current_user
    
    # Camada 3: verificar subscrição activa — trainer normal
    if current_user.role != "trainer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a Personal Trainers.",
        )
    
    from app.services.subscription_service import SubscriptionService

    subscription= SubscriptionService.get_subscription(session, current_user.id)

    if not SubscriptionService.has_active_access(subscription):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Acesso negado: requer subscrição activa. Por favor, aceda à página de billing para renovar ou actualizar a sua subscrição.",
        )
    return current_user

async def require_client(current_user = Depends(get_current_user)):
    """
    Garante que o utilizador autenticado é um cliente.
    Usado nas rotas do portal do cliente (/cliente/*).
    """

    if current_user.role != "client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a clientes.",
        )
    return current_user

def require_api_key(x_api_key: str = Header(default=None, alias="X-API-Key")) -> None:
    """
    Valida a API Key enviada no header X-API-Key.
 
    Aplicada globalmente a todos os routers como common_dependency em main.py.
    É a primeira barreira de segurança — impede acesso ao API surface
    por qualquer cliente não autorizado, antes mesmo da validação JWT.
    """

    if not settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key não configurada no servidor.",
        )

    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key inválida.",
        )