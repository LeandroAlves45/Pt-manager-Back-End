from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError
from datetime import date
from typing import Optional

from app.api.deps import db_session
from app.core.security import get_current_user, require_active_subscription
from app.schemas.client import ClientCreate, ClientRead, ClientUpdate, ClientReadWithPack, ActivePackInfo
from app.db.models.pack import PackType
from app.services.pack_service import PackService
from app.services.subscription_service import SubscriptionService
from app.db.models.client import Client
from app.core.db_errors import commit_or_rollback

router = APIRouter(prefix="/clients", tags=["Clients"])

#------------------------------
#Helper para definir o status do cliente
#------------------------------

def _client_status(client):
    # Determina status sem depender do tipo de archived_at
    # Se existir qualquer valor -> archived, senao active.
    

    return "archived" if client.archived_at else "active"

def _to_client_read(c: Client) -> ClientRead:

    # Converte model DB -> DTO de resposta.
  
    return ClientRead(
        id=c.id,
        full_name=c.full_name,
        phone=c.phone,
        email=c.email,
        birth_date=c.birth_date,
        sex=c.sex,
        height_cm=c.height_cm,
        objetive=getattr(c, "objetive", None),
        training_modality=getattr(c, "training_modality", "presencial"),
        next_assessment_date=getattr(c, "next_assessment_date", None),
        notes=c.notes,
        emergency_contact_name=getattr(c, "emergency_contact_name", None),
        emergency_contact_phone=getattr(c, "emergency_contact_phone", None),
        status=_client_status(c),
        created_at=c.created_at,
        updated_at=c.updated_at,
    )

def _build_client_with_pack(client: Client, session: Session) -> ClientReadWithPack:

    # Constrói ClientReadWithPack a partir do client e sessão DB.
    # Busca o pack ativo e inclui info relevante.


    active = PackService.get_active_pack(session, client_id=client.id)

    active_pack_info = None
    if active:
        pt = session.get(PackType, active.pack_type_id)
        if pt:
            ramaining = active.sessions_total_snapshot - active.sessions_used

            active_pack_info = ActivePackInfo(
                client_pack_id=active.id,
                pack_type_id=pt.id,
                pack_type_name=pt.name,
                sessions_total=active.sessions_total_snapshot,
                sessions_used=active.sessions_used,
                sessions_remaining=ramaining,
            )
    
    base = _to_client_read(client)
    base_data = base.model_dump() if hasattr(base, "model_dump") else base.dict()

    return ClientReadWithPack(**base_data, active_pack=active_pack_info)

def _get_trainer_id_filter(current_user) -> Optional[str]:
    
    # Retorna o trainer_id para filtrar clientes, ou None se não houver filtro.
    # Se o user for trainer, retorna seu próprio ID para filtrar apenas seus clientes.
    # Se for superuser, retorna None para não filtrar (ver todos os clientes).
   
    if current_user.role == "superuser":
        return None
    return current_user.id

#------------------------------
#Endpoints exclusivo para clientes, que inclui info do pack ativo
#------------------------------

@router.get("/me", response_model=ClientReadWithPack)
async def get_my_client_profile(
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user), #qualquer utilizador autenticado pode aceder ao seu perfil
) -> ClientReadWithPack:
  
    # Endpoint para o cliente autenticado ver o seu próprio perfil, incluindo info do pack ativo.
    # Colocação de "me" no path é uma prática comum para endpoints relacionados ao próprio usuário, evitando confusão com endpoints de administração ou listagem geral.

    if current_user.role != "client" or not current_user.client_id:
        raise HTTPException(status_code=403, detail="Acesso negado. Este endpoint é apenas para clientes autenticados.")
    
    client = session.get(Client, current_user.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Perfil de cliente não encontrado.")
    
    return _build_client_with_pack(client, session)
    
#------------------------------
#Endpoints de administração (trainers ou superusers) 
#------------------------------

@router.get("", response_model=list[ClientReadWithPack])
async def list_clients(
    Status: Optional[int] = None,
    Page_size: Optional[int] = None,
    Page_number: Optional[int] = None,
    session: Session = Depends(db_session),
    current_user= Depends(require_active_subscription), 
) -> list[ClientReadWithPack]:
    #Lista de todos os clientes com filtros opcionais. Trainer vê apenas os seus clientes, superuser vê todos os clientes.
    try:
        query = select(Client)
        trainer_id = _get_trainer_id_filter(current_user)
        if trainer_id:
            query = query.where(Client.owner_trainer_id == trainer_id)
        
        if Status ==1:
            query = query.where(Client.archived_at.is_(None))
        elif Status == 2:
            query = query.where(Client.archived_at.is_not(None))
        elif Status is not None:
            raise HTTPException(status_code=400, detail="Status inválido. Use 1 para ativos e 2 para arquivados.")
            
        if (Page_size is None) ^ (Page_number is None):
            raise HTTPException(status_code=400, detail="Page_size e Page_number devem ser fornecidos juntos para paginação.")
        
        if Page_size is not None and Page_number is not None:
            if Page_size <= 0 or Page_number <= 0:
                raise HTTPException(status_code=400, detail="Page_size e Page_number devem ser maiores que zero.")
            
            offset = (Page_number - 1) * Page_size
            query = query.offset(offset).limit(Page_size)

        clients = session.exec(query).all()
        return [_build_client_with_pack(c, session) for c in clients]
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao listar clientes.") from e
    
@router.get("/{client_id}", response_model=ClientReadWithPack)
async def get_client_details(
    client_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user), #qualquer utilizador autenticado pode ver detalhes do cliente
) -> ClientReadWithPack:
    #Detalhes de um cliente específico. Trainers apenas seus clientes, superuser vê todos e clientes veem apenas o seu registo.

    client = session.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    
    #Verificação de acesso
    if current_user.role == "client":
        if current_user.client_id != client_id:
            raise HTTPException(status_code=403, detail="Sem permissão.")
    
    elif current_user.role == "trainer":
        if client.owner_trainer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Sem permissão.")
    
    return _build_client_with_pack(client, session)

@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    session: Session = Depends(db_session),
    current_user = Depends(require_active_subscription), 
) -> Client:
    #Cria um novo cliente. 
    # Tem que ter subscrição ativa para criar clientes.
    # Pode adicionar clientes (limite de tier)
    # Unicidade do telemóvel e email

    #Verifica se o trainer pode adicionar mais clientes (superusers e isentos ignoram o limite)
    if current_user.role != "superuser" and not getattr(current_user, "is_exempt_from_billing", False):
        subscription = SubscriptionService.get_subscription(session, current_user.id)
        can_add, error_msg = SubscriptionService.can_add_client(subscription)
        if not can_add:
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=error_msg)
    

    try:
        existing_phone = session.exec(select(Client).where(Client.phone == payload.phone)).first()
        if existing_phone:
            raise HTTPException(status_code=409, detail="Telefone já existe.")
        
        if payload.email:
            email_str = str(payload.email)
            existing_email = session.exec(select(Client).where(Client.email == email_str)).first()
            if existing_email:
                raise HTTPException(status_code=409, detail="Email já existe.")
            
        else:
            email_str = None

        client = Client(
            full_name=payload.full_name,
            phone=payload.phone,
            email=email_str,
            birth_date=payload.birth_date,
            sex=payload.sex,
            height_cm=payload.height_cm,
            objetive=getattr(payload, "objetive", None),
            notes=payload.notes,
            emergency_contact_name=getattr(payload, "emergency_contact_name", None),
            emergency_contact_phone=getattr(payload, "emergency_contact_phone", None),
            owner_trainer_id=current_user.id, #associa cliente ao trainer que o criou
        )

        session.add(client)
        commit_or_rollback(session)
        session.refresh(client)
      
        #Atualiza a contagem de clientes e o tier no Stripe
        SubscriptionService.sync_client_count(session, current_user.id)

        return _to_client_read(client)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao criar cliente.") from e
    
@router.patch("/{client_id}", response_model=ClientRead)
async def update_client(
    client_id: str,
    payload: ClientUpdate,
    session: Session = Depends(db_session),
    current_user = Depends(require_active_subscription), #apenas trainers podem atualizar clientes
) -> Client:
    #Atualiza os dados de um cliente específico. Apenas trainers ou superuser podem atualizar clientes.
    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        #Verificação de acesso
        if current_user.role == "trainer" and client.owner_trainer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        
        data = payload.model_dump(exclude_unset=True)

        if "email" in data and data["email"] is not None:
            data["email"] = str(data["email"])

        if "phone" in data and data["phone"] != client.phone:
            existing_phone = session.exec(select(Client).where(Client.phone == data["phone"])).first()
            if existing_phone:
                raise HTTPException(status_code=409, detail="Telefone já existe.")

        if "email" in data and data["email"] != client.email and data["email"] is not None:
            existing_email = session.exec(select(Client).where(Client.email == data["email"])).first()
            if existing_email:
                raise HTTPException(status_code=409, detail="Email já existe.")

        for key, value in data.items():
            setattr(client, key, value)

        session.add(client)
        commit_or_rollback(session)
        session.refresh(client)
        return _to_client_read(client)
    
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao atualizar cliente.") from e
    
@router.post("/{client_id}/archive", response_model=ClientRead)
async def archive_client(
    client_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(require_active_subscription), #apenas trainers podem arquivar clientes
) -> Client:
    #Arquiva (soft delete) um cliente. Atualiza a contagem de clientes e o tier no Stripe.
    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        if current_user.role == "trainer" and client.owner_trainer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        
        if client.archived_at is None:
            from datetime import date
            client.archived_at = date.today()
            session.add(client)
            commit_or_rollback(session)
            session.refresh(client)

            #Atualiza a contagem de clientes e o tier no Stripe
            SubscriptionService.sync_client_count(session, client.owner_trainer_id)

        return _to_client_read(client)
    
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao arquivar cliente.") from e
    
@router.post("/{client_id}/unarchive", response_model=ClientRead)
async def unarchive_client(
    client_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(require_active_subscription), #apenas trainers podem reativar clientes
) -> Client:
    #Reativa um cliente. Verifica se trainer pode adicionar mais clientes.
    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        if current_user.role == "trainer" and client.owner_trainer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        
        if client.archived_at is not None:
            #Verifica se o trainer pode adicionar mais clientes antes de reativar (superusers e isentos ignoram o limite)
            if current_user.role != "superuser" and not getattr(current_user, "is_exempt_from_billing", False):
                subscription = SubscriptionService.get_subscription(session, current_user.id)
                can_add, error_msg = SubscriptionService.can_add_client(subscription)
                if not can_add:
                    raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=error_msg)
        
            client.archived_at = None
            session.add(client)
            commit_or_rollback(session)
            session.refresh(client)

            #Atualiza a contagem de clientes e o tier no Stripe
            SubscriptionService.sync_client_count(session, client.owner_trainer_id)

        return _to_client_read(client)
    
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao reativar cliente.") from e

@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: str,
    hard: bool = Query(default=False, description="hard=false -> arquiva, hard=true -> apaga da BD"),
    session: Session = Depends(db_session),
    current_user = Depends(require_active_subscription), #apenas trainers podem apagar clientes
) -> None:
    #Apaga ou arquiva o cliente. Apenas trainers podem apagar clientes.

    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        if current_user.role == "trainer" and client.owner_trainer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        
        trainer_id = client.owner_trainer_id
        
        if not hard:
            if client.archived_at is None:
                from datetime import date
                client.archived_at = date.today()
                session.add(client)
                commit_or_rollback(session)
                SubscriptionService.sync_client_count(session, trainer_id)
            return None
        
        session.delete(client)
        commit_or_rollback(session)
        SubscriptionService.sync_client_count(session, trainer_id)
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao apagar cliente.") from e
    
