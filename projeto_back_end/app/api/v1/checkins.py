"""
Router para Check-Ins periódicos.

Endpoints:
  POST   /check-ins/                           → trainer cria pedido
  GET    /check-ins/client/{client_id}         → trainer lista check-ins de um cliente
  GET    /check-ins/pending                    → cliente vê os seus check-ins pendentes
  POST   /check-ins/{checkin_id}/respond       → cliente responde ao check-in
  PATCH  /check-ins/{checkin_id}/trainer-notes → trainer adiciona notas
  POST   /check-ins/{checkin_id}/skip          → trainer ignora um check-in
"""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, status
from sqlmodel import Session, select

from app.api.deps import db_session
from app.core.security import get_current_user, require_active_subscription
from app.core.db_errors import commit_or_rollback
from app.db.models.checkin import CheckIn
from app.db.models.client import Client
from app.schemas.checkin import CheckInResponse, CheckInTrainerNotes, CheckInRead, CheckInCreate

router = APIRouter(prefix="/check-ins", tags=["Check-Ins"])

@router.post("/", response_model=CheckInRead, status_code=status.HTTP_201_CREATED)
async def create_checkin(payload:CheckInCreate, session: Session = Depends(db_session), current_user=Depends(require_active_subscription)):
    #trainer cria um pedido de check-in para um cliente

    try:
        #verificar se o cliente existe e pertence ao trainer
        client = session.get(Client, payload.client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
        #Verificar se o cliente pertence ao trainer
        if current_user.role == "trainer" and client.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Sem permissão.")
    
        checkin = CheckIn(
            client_id=payload.client_id,
            requested_by_trainer_id=current_user.id,
            status="pending"
        )
        session.add(checkin)
        commit_or_rollback(session)
        session.refresh(checkin)
        return CheckInRead.model_validate(checkin)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/client/{client_id}", response_model=list[CheckInRead])
async def list_checkins_for_client(client_id: str, session: Session = Depends(db_session), current_user=Depends(require_active_subscription)):
    #trainer lista os check-ins de um cliente (por ordem mais recente)

    try:
        #verificar se o cliente existe e pertence ao trainer
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")

        #Verificar se o cliente pertence ao trainer
        if current_user.role == "trainer" and client.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Sem permissão.")

        checkins = session.exec(select(CheckIn).where(CheckIn.client_id == client_id).order_by(CheckIn.created_at.desc())).all()
        return [CheckInRead.model_validate(c) for c in checkins]
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pending", response_model=list[CheckInRead])
async def get_my_pending_checkins(session: Session = Depends(db_session), current_user=Depends(get_current_user)):
    #cliente vê os seus check-ins pendentes

    try:
        if current_user.role != "client" or not current_user.client_id:
            raise HTTPException(status_code=403, detail="Endpoint apenas para clientes.")
        
        checkins = session.exec(select(CheckIn).where(CheckIn.client_id == current_user.client_id, CheckIn.status == "pending").order_by(CheckIn.created_at.desc())).all()
        return [CheckInRead.model_validate(c) for c in checkins]
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{checkin_id}/respond", response_model=CheckInRead)
async def respond_to_checkin(checkin_id: str, payload: CheckInResponse, session: Session = Depends(db_session), current_user=Depends(get_current_user)):
    #cliente responde a um check-in pendente
    try:

        checkin = session.get(CheckIn, checkin_id)
        if not checkin:
            raise HTTPException(status_code=404, detail="Check-in não encontrado.")
        
        if current_user.role != "client" and checkin.client_id != current_user.client_id:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        
        if checkin.status == "completed":
            raise HTTPException(status_code=400, detail="Check-in já foi respondido.")
        
        if checkin.status == "skipped":
            raise HTTPException(status_code=400, detail="Check-in foi ignorado pelo Personal Trainer.")
        
        #Atualizar os dados do check-in com a resposta do cliente
        checkin.weight_kg = payload.weight_kg
        checkin.body_fat = payload.body_fat
        checkin.client_notes = payload.client_notes

        if payload.questionnaire:
            checkin.questionnaire = payload.questionnaire.model_dump(exclude_none=True)

        if payload.photos:
            checkin.photos = {"photos": [p.model_dump() for p in payload.photos]} #ex: {"photos": [{"photo_type": "front", "url": "url1"}, ...]}
        
        checkin.status = "completed"
        checkin.completed_at = datetime.now(timezone.utc)
        
        session.add(checkin)
        commit_or_rollback(session)
        session.refresh(checkin)
        return CheckInRead.model_validate(checkin)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{checkin_id}/trainer-notes", response_model=CheckInRead)
async def add_trainer_notes(checkin_id: str, payload: CheckInTrainerNotes, session: Session = Depends(db_session), current_user=Depends(require_active_subscription)):
    #trainer adiciona notas a um check-in respondido

    try:
        checkin = session.get(CheckIn, checkin_id)
        if not checkin:
            raise HTTPException(status_code=404, detail="Check-in não encontrado.")
        
        if current_user.role != "trainer" and checkin.requested_by_trainer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        
        if checkin.status != "completed":
            raise HTTPException(status_code=400, detail="Só é possível adicionar notas a check-ins respondidos.")
        
        checkin.trainer_notes = payload.trainer_notes
        
        session.add(checkin)
        commit_or_rollback(session)
        session.refresh(checkin)
        return CheckInRead.model_validate(checkin)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/{checkin_id}/skip", response_model=CheckInRead)
async def skip_checkin(checkin_id: str, session: Session = Depends(db_session), current_user=Depends(require_active_subscription)):
    #trainer ignora um check-in (status passa para "skipped")

    try:
        checkin = session.get(CheckIn, checkin_id)
        if not checkin:
            raise HTTPException(status_code=404, detail="Check-in não encontrado.")
        
        if current_user.role != "trainer" and checkin.requested_by_trainer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        
        if checkin.status == "completed":
            raise HTTPException(status_code=400, detail="Check-in já foi respondido.")
        
        checkin.status = "skipped"
        session.add(checkin)
        commit_or_rollback(session)
        session.refresh(checkin)
        return CheckInRead.model_validate(checkin)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))