"""
Router de autenticação — endpoints de login e gestão de utilizadores.

Estrutura dos endpoints:
    POST /auth/login          — login público (não requer token)
    POST /auth/users          — criar utilizador (apenas trainers)
    GET  /auth/users          — listar utilizadores (apenas trainers)
    GET  /auth/users/me       — ver o próprio perfil (qualquer utilizador autenticado)
    PATCH /auth/users/{id}    — atualizar utilizador (trainer ou o próprio user)
    POST /auth/users/me/change-password — alterar própria password
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.api.deps import db_session
from app.core.security import (
    get_current_user,
    require_trainer,
    create_access_token,
    verify_password,
    hash_password,
)
from app.db.models.user import User
from app.db.models.client import Client
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

    #Processo:
    #1. Busca o utilizador pelo email
    #2. Verifica a password com bcrypt (compare hash)
    #3. Verifica se a conta está ativa
    #4. Gera e devolve o JWT

    #Nota de segurança: devolvemos sempre o mesmo erro (401) se email não existe
    #ou se a password está errada. Isto evita "user enumeration" — um atacante
    #não consegue descobrir se um email está registado ou não.

    

    # Verificar se o email existe
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou password inválidos")

    # Verificar se a password está correta, se não, devolver o mesmo erro genérico
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou password inválidos")
    
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Conta inativa. Contacte o seu treinador.")

    #3. Criar token JWT com role e user_id
    token_data = create_access_token(
        subject=user.id,
        role=user.role,
        full_name=user.full_name,
    )
    

    return TokenOut(access_token=token_data, role=user.role, user_id=user.id, full_name=user.full_name)

#------------------------------
#Gestão de utilizadores - apenas trainers podem criar e listar utilizadores
#------------------------------

@router.post("/users", status_code=status.HTTP_201_CREATED, response_model=UserRead)
async def create_user(
    payload: UserCreate,
    session: Session = Depends(db_session),
    _trainer = Depends(require_trainer), #apenas trainers podem criar utilizadores
) -> UserRead:
    #Cria um novo utilizador. Apenas trainers podem criar.

    #Processo:
    #1. Verificar se o email já existe (único)
    #2. Criar hash da password com bcrypt
    #3. Criar o utilizador na DB
    #4. Devolver os dados do utilizador criado (sem password)

    #Verificar se o email já existe
    existing_user = session.exec(select(User).where(User.email == payload.email)).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409, detail="Email já registado")
    
    #Se o role é "client", verificar se o client_id existe na tabela de clientes
    if payload.role == "client" and payload.client_id:
        client_exists = session.get(Client, payload.client_id)
        if not client_exists:
            raise HTTPException(status_code=status.HTTP_404, detail="Cliente não encontrado")
        
        #Verificar se o cliente já tem um utilizador associado
        already_linked= session.exec(
            select(User).where(User.client_id == payload.client_id)
        ).first()
        if already_linked:
            raise HTTPException(status_code=status.HTTP_409, detail="Cliente já tem um utilizador associado")

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
    _trainer = Depends(require_trainer), #apenas trainers podem listar utilizadores
) -> list[UserRead]:
    #Lista todos os utilizadores. Apenas trainers podem listar.

    users = session.exec(select(User)).all()
    return [UserRead.model_validate(u) for u in users]

#------------------------------
# Rotas do utilizador autenticado - qualquer utilizador pode ver e atualizar o próprio perfil
#------------------------------

@router.get("/users/me", response_model=UserRead)
async def get_my_profile(
    current_user = Depends(get_current_user), #qualquer utilizador autenticado pode ver o próprio perfil
) -> UserRead:
    #Devolve os dados do próprio utilizador (sem password)
    return UserRead.model_validate(current_user)

@router.post("/users/me/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    payload: ChangePassword,
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user), #qualquer utilizador autenticado pode alterar a própria password
) -> dict:
    #Permite ao utilizador alterar a própria password.

    #Processo:
    #1. Verificar se a current_password está correta
    #2. Se estiver, atualizar para a new_password (hash)

    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password atual incorreta")

    current_user.hashed_password = hash_password(payload.new_password)
    current_user.updated_at = datetime.utcnow()
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
    #Permite atualizar os dados de um utilizador. Trainers podem atualizar qualquer utilizador, 
    #enquanto um user pode atualizar apenas o próprio perfil.

    if current_user.role == "client" and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para atualizar este utilizador")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilizador não encontrado")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)  

    user.updated_at = datetime.utcnow()
    session.add(user)
    try:
        session.commit()
        session.refresh(user)
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro ao atualizar utilizador: ") from e

    return UserRead.model_validate(user)
