"""
Router de autenticação — endpoints de login e gestão de utilizadores.

Estrutura dos endpoints:
    POST /auth/login                    — login público (não requer token)
    POST /auth/logout                   — logout (requer token, invalida o token atual)
    POST /auth/users                    — criar utilizador (apenas trainers)
    GET  /auth/users                    — listar utilizadores (apenas trainers)
    GET  /auth/users/me                 — ver o próprio perfil (qualquer utilizador autenticado)
    PATCH /auth/users/{id}              — atualizar utilizador (trainer ou o próprio user)
    POST /auth/users/me/change-password — alterar própria password
"""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.api.deps import db_session
from app.core.config import settings
from app.core.security import (
    get_current_user,
    require_trainer,
    create_access_token,
    verify_password,
    hash_password,
)
from app.db.models.user import User
from app.db.models.client import Client
from app.db.models.active_token import ActiveToken
from app.schemas.auth import (
    LoginIn,
    TokenOut,
    UserCreate,
    UserRead,
    ChangePassword,
    UserUpdate,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

#------------------------------
# Endpoints de login - públicos, sem necessidade de token
#------------------------------

@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, session: Session = Depends(db_session)) -> TokenOut:
    #Autentica um utilizador e devolve um JWT access token.
    #Nota de segurança: devolvemos sempre o mesmo erro (401) se email não existe
    #ou se a password está errada. Isto evita "user enumeration" — um atacante
    #não consegue descobrir se um email está registado ou não.

    

    # Busca o utilizador pelo email.
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou password inválidos")

    # Verificar se a password corresponde ao hash armazenado.
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou password inválidos")
    
    # Conta inativa - trainer suspenso pelo superuser. por exemplo
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Conta inativa. Entra em contacto com o suporte.")

    # Cria JWT
    expire_delta = timedelta(minutes=settings.access_token_expire_minutes)
    token_str = create_access_token(
        subject=user.id,
        role=user.role,
        full_name=user.full_name,
        expires_delta=expire_delta,
    )
 
    # Persistir o token na base de dados para permitir logout e controlo de sessões ativas.
    existing = session.exec(
        select(ActiveToken).where(ActiveToken.user_id == user.id)
    ).first()

    if existing:
        session.delete(existing)
        session.flush()  
 
    expires_at = datetime.now(timezone.utc) + expire_delta
    active_token = ActiveToken(
        user_id=user.id,
        token=token_str,
        expires_at=expires_at,
    )
    session.add(active_token)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro ao persistir token de sessão.") from e
 
    return TokenOut(
        access_token=token_str,
        role=user.role,
        user_id=user.id,
        full_name=user.full_name,
    )

#------------------------------
# Endpoint de logout - invalida o token atual
#------------------------------

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user),
) -> dict:
    # Invalida o token atual do utilizador, removendo-o da base de dados.
    # O token é enviado no header Authorization

    active_token = session.exec(
        select(ActiveToken)
        .where(ActiveToken.user_id == current_user.id)
    ).first()

    if active_token:
        session.delete(active_token)
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail="Erro ao invalidar token de sessão.") from e
        
    return {"detail": "Logout bem-sucedido"}

#------------------------------
#Gestão de utilizadores - apenas trainers podem criar e listar utilizadores
#------------------------------

@router.post("/users", status_code=status.HTTP_201_CREATED, response_model=UserRead)
async def create_user(
    payload: UserCreate,
    session: Session = Depends(db_session),
    current_trainer = Depends(require_trainer), #apenas trainers podem criar utilizadores
) -> UserRead:
    #Cria um novo utilizador. (Tipicamente um cliente de um trainer)

    #Processo:
    #1. Verificar se o email já existe (único)
    #2. Se o role é "client", verificar se o client_id existe na tabela de clientes e se já tem um utilizador associado
    #3. Cria hash bcrypt da password - nunca armazenar passwords em texto simples!
    #4. Persiste o utilizador na base de dados e devolve os dados do utilizador criado (sem password)

    #Verificar se o email já existe, email é único
    existing_user = session.exec(select(User).where(User.email == payload.email)).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email já registado")
    
    #Se o role é "client", verificar se o cliente existe na tabela de clientes
    if payload.role == "client" and payload.client_id:
        client_exists = session.get(Client, payload.client_id)
        if not client_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
        
        # Impede associar dois utilizadores ao mesmo cliente
        already_linked= session.exec(
            select(User).where(User.client_id == payload.client_id)
        ).first()
        if already_linked:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cliente já tem um utilizador associado")

    #Criar o utilizador- convertendo a password para hash
    new_user = User(
        email=str(payload.email),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        client_id=payload.client_id if payload.role == "client" else None,
    )
    session.add(new_user)
    try:
        session.commit()
        session.refresh(new_user)
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro ao criar utilizador: ") from e

    #Devolver os dados do utilizador criado (sem password)
    return UserRead.model_validate(new_user)

@router.get("/users", response_model=list[UserRead])
async def list_users(
    session: Session = Depends(db_session),
    current_trainer = Depends(require_trainer), #apenas trainers podem listar utilizadores
) -> list[UserRead]:
    # Lista todos os utilizadores (clientes) pertencentes ao trainer autenticado.
    # Superuser pode listar todos os utilizadores (clientes).

    if current_trainer.role == "superuser":
        users = session.exec(select(User)).all()

    else:
        # Trainers só vê os utilizadores cujos clientes lhe pertencem
        users = session.exec(
            select(User)
            .join(Client, User.client_id == Client.id)
            .where(Client.owner_trainer_id == current_trainer.id)
        ).all()

    return [UserRead.model_validate(user) for user in users]


#------------------------------
# Rotas do utilizador autenticado - qualquer role pode ver e atualizar o próprio perfil
#------------------------------

@router.get("/users/me", response_model=UserRead)
async def get_my_profile(
    current_user = Depends(get_current_user), 
) -> UserRead:
    #Devolve os dados do próprio utilizador (sem password)
    return UserRead.model_validate(current_user)

@router.post("/users/me/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    payload: ChangePassword,
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user), 
) -> dict:
    # Permite ao utilizador alterar a própria password.

    # Requer a password atual para confirmar a identidade do utilizador. Isto é uma medida de segurança importante,

    # Confirma que a password atual está correta antes de permitir a alteração.
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password atual incorreta.")

    current_user.hashed_password = hash_password(payload.new_password)
    current_user.updated_at = datetime.now(timezone.utc)
    session.add(current_user)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro ao alterar password: ") from e

    return {"detail": "Password alterada com sucesso"}

@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user), #trainer ou o próprio user podem atualizar
) -> UserRead:
    # Permite atualizar os dados de um utilizador. Trainers podem atualizar qualquer utilizador, 
    # Regras de acesso:
    # - Clients só podem atualizar o próprio perfil
    # - Trainers podem atualizar qualquer utilizador do seu tenant
    # - Superusers podem atualizar qualquer utilizador

    # Clientes só podem editar o próprio perfil
    if current_user.role == "client" and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para atualizar este utilizador.")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilizador não encontrado.")

    # model_dump(exclude_unset=True) garante que apenas os campos enviados são atualizados -- Patch parcial
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)  

    user.updated_at = datetime.now(timezone.utc)
    session.add(user)
    try:
        session.commit()
        session.refresh(user)
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro ao atualizar utilizador: ") from e

    return UserRead.model_validate(user)
