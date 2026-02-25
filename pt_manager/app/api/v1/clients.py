from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional

from app.api.deps import db_session
from app.core.security import get_current_user, require_trainer
from app.schemas.client import ClientCreate, ClientRead, ClientUpdate, ClientReadWithPack, ActivePackInfo
from app.db.models.pack import PackType
from app.services.pack_service import PackService
from app.db.models.client import Client
from app.core.db_errors import commit_or_rollback

router = APIRouter(prefix="/clients", tags=["Clients"])

#------------------------------
#Helper para definir o status do cliente
#------------------------------

def _client_status(client):
    """
    Determina status sem depender do tipo de archived_at
    Se existir qualquer valor -> archived, senao active.
    """

    return "archived" if client.archived_at else "active"

def _to_client_read(c: Client) -> ClientRead:
    """
    Converte model DB -> DTO de resposta.
    """
    return ClientRead(
        id=c.id,
        full_name=c.full_name,
        phone=c.phone,
        email=c.email,
        birth_date=c.birth_date,
        sex=c.sex,
        height_cm=c.height_cm,
        objetive=getattr(c, "objetive", None),
        notes=c.notes,
        emergency_contact_name=getattr(c, "emergency_contact_name", None),
        emergency_contact_phone=getattr(c, "emergency_contact_phone", None),
        status=_client_status(c),
        created_at=c.created_at,
        updated_at=c.updated_at,
    )

def _build_client_with_pack(client: Client, session: Session) -> ClientReadWithPack:
    """
    Constrói ClientReadWithPack a partir do client e sessão DB.
    Busca o pack ativo e inclui info relevante.
    """

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

#------------------------------
#Endpoints exclusivo para clientes, que inclui info do pack ativo
#------------------------------

@router.get("/me", response_model=list[ClientReadWithPack])
async def get_my_client_profile(
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user), #qualquer utilizador autenticado pode aceder ao seu perfil
) -> list[ClientReadWithPack]:
    """
    Endpoint para o cliente autenticado ver o seu próprio perfil, incluindo info do pack ativo.

    Colocação de "me" no path é uma prática comum para endpoints relacionados ao próprio usuário, evitando confusão com endpoints de administração ou listagem geral.
    """
    if current_user.role != "client" or not current_user.client_id:
        raise HTTPException(status_code=403, detail="Acesso negado. Este endpoint é apenas para clientes autenticados.")
    
    client = session.get(Client, current_user.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Perfil de cliente não encontrado.")
    
    return _build_client_with_pack(client, session)
    
#------------------------------
#Endpoints de administração (trainers) 
#------------------------------

@router.get("", response_model=list[ClientReadWithPack])
async def list_clients(
    Client_id: Optional[str] = None,
    Status: Optional[int] = None,
    Page_size: Optional[int] = None,
    Page_number: Optional[int] = None,
    session: Session = Depends(db_session),
    _trainer = Depends(require_trainer), #apenas trainers podem listar clientes
) -> list[ClientReadWithPack]:
    #Lista de todos os clientes com filtros opcionais. Apenas trainers podem listar clientes.
    try:
        query = select(Client)
        if Client_id:
            query = query.where(Client.id == Client_id)
        
        if Status is not None:
            if Status == 1: #Ativos
                query = query.where(Client.archived_at.is_(None))
            elif Status == 2: #Arquivados
                query = query.where(Client.archived_at.is_not(None))
            else:
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
    
@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    session: Session = Depends(db_session),
    _trainer = Depends(require_trainer), #apenas trainers podem criar clientes
) -> Client:
    #Cria um novo cliente. Apenas trainers podem criar clientes.
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
        )

        session.add(client)
        commit_or_rollback(session)
        session.refresh(client)
        return _to_client_read(client)
    
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao criar cliente.") from e
    
@router.get("/{client_id}", response_model=ClientReadWithPack)
async def get_client_details(
    client_id: str,
    session: Session = Depends(db_session),
    current_user = Depends(get_current_user), #qualquer utilizador autenticado pode ver detalhes do cliente
) -> ClientReadWithPack:
    #Detalhes de um cliente específico. Trainers veem tudo, clientes veem apenas o seu registo.

    if current_user.role == "client" and current_user.client_id != client_id:
        raise HTTPException(status_code=403, detail="Acesso negado. Clientes só podem acessar seus próprios detalhes.")
    
    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        if current_user.role == "client" and client.archived_at is not None:
            raise HTTPException(status_code=404, detail="Acesso negado a cliente arquivado.")
        
        return _build_client_with_pack(client, session)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro inesperado ao obter detalhes do cliente.") from e
    
@router.patch("/{client_id}", response_model=ClientRead)
async def update_client(
    client_id: str,
    payload: ClientUpdate,
    session: Session = Depends(db_session),
    _trainer = Depends(require_trainer), #apenas trainers podem atualizar clientes
) -> Client:
    #Atualiza os dados de um cliente específico. Apenas trainers podem atualizar clientes.
    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
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
    _trainer = Depends(require_trainer), #apenas trainers podem arquivar clientes
) -> Client:
    #Arquiva (soft delete) um cliente. Apenas trainers podem arquivar clientes.
    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        if client.archived_at is None:
            from datetime import date
            client.archived_at = date.today()
            session.add(client)
            commit_or_rollback(session)
            session.refresh(client)

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
    _trainer = Depends(require_trainer), #apenas trainers podem reativar clientes
) -> Client:
    #Reativa um cliente. Apenas trainers podem reativar clientes.
    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        if client.archived_at is not None:
            client.archived_at = None
            session.add(client)
            commit_or_rollback(session)
            session.refresh(client)

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
    _trainer = Depends(require_trainer), #apenas trainers podem apagar clientes
) -> None:
    #Apaga ou arquiva o cliente. Apenas trainers podem apagar clientes.

    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        if not hard:
            if client.archived_at is None:
                from datetime import date
                client.archived_at = date.today()
                session.add(client)
                commit_or_rollback(session)
            return None
        
        session.delete(client)
        commit_or_rollback(session)
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao apagar cliente.") from e
    
#------------------------------
#Endpoints de clientes
#------------------------------

@router.get("", response_model=list[ClientReadWithPack])
async def list_clients(Client_id: Optional[str] = None, 
                 Status: Optional[int] = None, 
                 Page_size: Optional[int] = None, 
                 Page_number: Optional[int] = None, 
                 session: Session = Depends(db_session)
) -> list[ClientReadWithPack]:
    """
    Lista de todos os clientes com filtros opcionais
    """

    try:
        stmt = select (Client)

        #filtro por client_id
        if Client_id:
            stmt = stmt.where(Client.id == Client_id)

        #filtro por status
        if Status is not None: 
            if Status == 1: #Ativos
                stmt = stmt.where(Client.archived_at.is_(None))

            elif Status == 2: #arquivados
                stmt = stmt.where(Client.archived_at.is_not(None))
            else:
                raise HTTPException(status_code=400, detail="Status inválido. Use 1 para ativos e 2 para arquivados.")
        
        #paginação
        if (Page_size is None) ^ (Page_number is None):
            raise HTTPException(status_code=400, detail="Page_size e Page_number devem ser fornecidos juntos para paginação.")

        if Page_size is not None and Page_number is not None:
            if Page_size <= 0 or Page_number <= 0:
                raise HTTPException(status_code=400, detail="Page_size e Page_number devem ser maiores que zero.")

            offset = (Page_number - 1) * Page_size
            stmt = stmt.offset(offset).limit(Page_size)
        
        #executa query
        clients = session.exec(stmt).all()

        #constrói resposta com info do pack ativo
        result: list[ClientReadWithPack] = []

        for client in clients:
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

            result.append(ClientReadWithPack(**base_data, active_pack=active_pack_info))
        
        return result

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao listar clientes.") from e



@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
async def create_client(payload: ClientCreate, session: Session = Depends(db_session)) -> Client:
    """
    Cria um novo cliente.
    Não permite criar clientes já arquivados.
    Unicidade do email é verificada em services.
    Nesta fase, validamos também a nível de app para devolver erro amigável.
    """
    try:
        # Validação amigável (a constraint UNIQUE será a garantia final)
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
        )

        session.add(client)
        commit_or_rollback(session)
        session.refresh(client)
        return _to_client_read(client)

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao criar cliente.") from e



@router.patch("/{client_id}", response_model=ClientRead)
async def update_client(client_id: str, payload: ClientUpdate, session: Session = Depends(db_session)) -> Client:
    """
    Update parcial do cliente
    Atualiza os dados de um cliente específico.
    Não permite atualizar clientes arquivados.
    """

    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")

        data = payload.model_dump(exclude_unset=True)

        # Normaliza email -> str
        if "email" in data and data["email"] is not None:
            data["email"] = str(data["email"])

        # Unicidade phone
        if "phone" in data and data["phone"] != client.phone:
            existing_phone = session.exec(select(Client).where(Client.phone == data["phone"])).first()
            if existing_phone:
                raise HTTPException(status_code=409, detail="Telefone já existe.")

        # Unicidade email
        if "email" in data and data["email"] != client.email and data["email"] is not None:
            existing_email = session.exec(select(Client).where(Client.email == data["email"])).first()
            if existing_email:
                raise HTTPException(status_code=409, detail="Email já existe.")

        # Aplica update
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
async def archive_client(client_id: str, session: Session = Depends(db_session)) -> Client:
    """
    Arquiva (soft delete) um cliente.
    """

    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")

        if client.archived_at is None:
            from datetime import date
            client.archived_at = date.today()
            session.add(client)
            commit_or_rollback(session)
            session.refresh(client)

        return _to_client_read(client)

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao arquivar cliente.") from e

@router.post("/{client_id}/unarchive", response_model=ClientRead)
async def unarchive_client(client_id: str, session: Session = Depends(db_session)) -> Client:
    """
    Reativa um cliente.
    """

    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")

        if client.archived_at is not None:
            client.archived_at = None
            session.add(client)
            commit_or_rollback(session)
            session.refresh(client)

        return _to_client_read(client)

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao reativar cliente.") from e

@router.delete ("/{client_id}", status_code= 204)
async def delete_client(client_id : str, hard: bool = Query(default = False, description = "hard=false -> arquiva, hard=true -> apaga da BD"), session: Session = Depends(db_session),) -> None:
    """
    Delete do cliente.

    hard false (default):
    -comporta-se como 'archive' (soft delete)
    -preserva histórico

    hard= true
    -apaga mesmo na BD
    -no futuro, pode falhar por FKs
    """

    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")

        if not hard:
            if client.archived_at is None:
                from datetime import date
                client.archived_at = date.today()
                session.add(client)
                commit_or_rollback(session)
            return None

        session.delete(client)
        commit_or_rollback(session)
        return None

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao apagar cliente.") from e