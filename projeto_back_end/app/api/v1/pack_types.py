from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import db_session
from app.db.models.pack import PackType
from app.schemas.pack_types import PackTypeCreate, PackTypeUpdate, PackTypeRead
from app.core.db_errors import commit_or_rollback

router = APIRouter(prefix="/pack-types", tags=["Pack-Types"])


@router.get("", response_model=list[PackTypeRead])
async def list_pack_types(session: Session = Depends(db_session)) -> list[PackTypeRead]:
    """
    Lista todos os tipos de pack.
    """

    try:
        stmt = select(PackType).order_by(PackType.name)
        return session.exec(stmt).all()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao listar Pack Types.") from e

@router.post("", response_model=PackTypeRead, status_code=status.HTTP_201_CREATED)
async def create_pack_type(payload: PackTypeCreate, session: Session = Depends(db_session)) -> PackType:
    """
    Cria um novo tipo de pack
    """
    try:
        existing = session.exec(select(PackType).where(PackType.name == payload.name)).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Pack Type com este nome já existe: '{payload.name}'",
            )
        """
        Cria um novo tipo de pack.
        """
        pack_type = PackType(name = payload.name, sessions_total=payload.sessions_total)
        session.add(pack_type)
        session.commit()
        session.refresh(pack_type)
        return pack_type

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao criar Pack Type.") from e


@router.put("/{pack_type_id}", response_model= PackTypeRead)
async def update_pack_type(pack_type_id: str,
    payload: PackTypeUpdate,
    session: Session = Depends(db_session),
) -> PackType:

    try:
        pack_type = session.get(PackType, pack_type_id)
        if not pack_type:
            raise HTTPException (status_code = 404, detail = "Pack Type não encontrado.")

        #se mudar de nome, validar
        if payload.name is not None and payload.name != pack_type.name:
            existing = session.exec(
                select(PackType).where(PackType.name == payload.name)
            ).first()
        
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Já existe Pack Type com este nome: '{payload.name}'",)
        
        pack_type.name = payload.name

        #atualizar sessions_total se mandado
        if payload.sessions_total is not None:
            pack_type.sessions_total = payload.sessions_total

        #atualizar is_active se enviado
        if payload.is_active is not None:
            pack_type.is_active = payload.is_active

        session.add(pack_type)
        commit_or_rollback(session)
        session.refresh(pack_type)
        return pack_type

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao atualizar Pack Type.") from e


@router.delete("/{pack_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pack_type(pack_type_id: str , session: Session = Depends(db_session)) -> None:
    """
    Elimina um tipo de pack pelo ID.
    """
    try:
        pack_type = session.get(PackType, pack_type_id)
        if not pack_type:
            raise HTTPException(status_code=404, detail="Pack Type não encontrado.")

        session.delete(pack_type)
        commit_or_rollback(session)
        return None

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro ao apagar Pack Type.") from e