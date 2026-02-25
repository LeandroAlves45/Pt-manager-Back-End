"""
Módulo de segurança.

Adicionadas dependencies:
    require_superuser          — apenas superusers
    require_active_subscription — trainer com subscrição activa (usado na maioria das rotas)
    get_trainer_subscription   — injecta a subscrição do trainer no handler (quando precisas de dados dela)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Header, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from app.core.config import settings
from app.api.deps import db_session

#--------------------------------------------
# Hash de passwords
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

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
ALGORITHM = "HS256"

def create_access_token(subject: str, role: str, full_name: str, client_id: str = None, expires_delta: Optional[timedelta] = None) -> str:
    """Cria um token JWT com as claims necessárias para autenticação e controlo de acesso."""

    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    payload = { 
        "sub": subject, 
        "role": role,
        "full_name": full_name,
        "exp": expire }
    if client_id is not None:
        payload["cid"] = client_id

    encoded_jwt = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)

    return encoded_jwt

#--------------------------------------------
# Dependencies de segurança
#--------------------------------------------

async def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(db_session)):
    """
    Valida o JWT e retorna o utilizador autenticado.
    Lança HTTPException 401 se o token for inválido ou expirado.
    """

    from app.db.models.user import User
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de autenticação inválido ou expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    from app.db.models.user import User
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exception
    
    return user

async def require_superuser(current_user = Depends(get_current_user)):
    """
    Dependency que garante que o utilizador autenticado é um superuser.
    Lança HTTPException 403 se o utilizador não for superuser.
    """
    if current_user.role != "superuser":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: requer privilégios de superuser.",
        )
    return current_user

async def require_trainer(current_user = Depends(get_current_user)):
    """
    Garante que o utilizador é um trainer (ou superuser — que tem acesso a tudo).
    NÃO verifica subscrição — para rotas que devem funcionar mesmo sem subscrição activa
    (ex: ver billing, aceder ao portal de pagamento).
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

    Verifica em cascata:
        1. É trainer ou superuser? (superuser passa sempre)
        2. Tem subscrição?
        3. A subscrição está activa (trial válido ou paid activo)?

    Uso: todas as rotas de gestão de clientes, planos, avaliações, etc.
    NÃO usar em: rotas de billing, login, signup.

    Lança 402 Payment Required se a subscrição não estiver activa —
    o 402 é semanticamente correcto: "tens de pagar para aceder a isto".
    """

    #Superusers têm acesso a tudo, independentemente de subscrição
    if current_user.role == "superuser":
        return current_user
    #Apenas trainers têm subscrição
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
    """Garante que o utilizador é um cliente (ou superuser — que tem acesso a tudo)."""
    if current_user.role != "client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a clientes.",
        )
    return current_user

def require_api_key(x_api_key: str = Header(default=None, alias="X-API-Key")) -> None:
    """
        Valida  API Key enviada no header X-API-Key.  
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