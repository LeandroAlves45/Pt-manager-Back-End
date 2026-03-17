"""
Router do portal do cliente — endpoints exclusivos para role="client".
 
Todos os endpoints usam o JWT para identificar o cliente automaticamente
via current_user.client_id — o cliente nunca precisa de saber o seu próprio ID.
 
Endpoints:
    GET /portal/my-profile          — perfil do cliente autenticado
    GET /portal/my-plan             — plano de treino activo (com dias e exercícios)
    GET /portal/my-meal-plans       — planos alimentares activos
    GET /portal/my-check-ins        — check-ins (pendentes e recentes)
    POST /portal/check-ins/{id}/respond — responder a um check-in pendente
"""

from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import db_session
from app.core.security import require_client
from app.core.db_errors import commit_or_rollback
from app.db.models.client import Client
from app.db.models.training import (
    TrainingPlan,
    TrainingPlanDay,
    PlanDayExercise,
    PlanExerciseSetLoad,
    ClientActivePlan,
    Exercise,
)
from app.db.models.client_supplement import ClientSupplement
from app.db.models.supplement import Supplement
from app.schemas.client_supplement import ClientSupplementPublic
from app.db.models.checkin import CheckIn
from app.schemas.checkin import CheckInResponse, CheckInRead
import app.crud.nutrition as nutrition_crud

router = APIRouter(prefix="/portal", tags=["Client Portal"])

# ----------------------------------
# Helper: valida que o utilizador tem client_id no JWT
# ----------------------------------

def _get_client_id(current_user) -> str:
    """
    Extrai o client_id do utilizador autenticado.
    Lança 403 se não for um cliente com client_id válido.
    """
    if not current_user.client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta de cliente sem perfil associado. Contacta o teu treinador."
        )
    return current_user.client_id

# ==================================================
# GET /portal/my-profile
# ==================================================

@router.get("/my-profile")
async def get_my_profile(
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> dict:
    # Retorna o perfil do cliente autenticado, incluindo dados biométricos, objetivo e modalidades de treino.

    try:
        client_id = _get_client_id(current_user)
        client = session.get(Client, client_id)

        if not client:
            raise HTTPException(status_code=404, detail="Perfil de cliente não encontrado.")
        
        return {
            "id": client.id,
            "full_name": client.full_name,
            "email": client.email,
            "phone": client.phone,
            "birth_date": str(client.birth_date) if client.birth_date else None,
            "sex": client.sex,
            "height_cm": client.height_cm,
            "training_modality": client.training_modality,
            "objective": client.objective,
            "notes": client.notes,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter perfil do cliente: {e}")
    
# ==================================================
# GET /portal/my-plan
# ==================================================

@router.get("/my-plan")
async def get_my_training_plan(
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> dict:
    # Devolve o plano de treino ativo do cliente autenticado com todos os dias e exercícios detalhados.

    try:
        client_id = _get_client_id(current_user)

        # Busca o registo de plano ativo 
        active_plan = session.exec(
            select(ClientActivePlan)
            .where(
                ClientActivePlan.client_id == client_id,
                ClientActivePlan.active_to == None
            )
        ).first()

        if not active_plan:
            return {"active_plan": None, "plan": None, "days": []}
        
        # Busca o plano de treino associado
        plan = session.get(TrainingPlan, active_plan.training_plan_id)
        if not plan:
            return {"active_plan": None, "plan": None, "days": []}
        
        # Busca os dias do plano, ordenados pelo índice
        days = session.exec(
            select(TrainingPlanDay)
            .where(TrainingPlanDay.training_plan_id == plan.id)
            .order_by(TrainingPlanDay.order_index)
        ).all()

        # Para cada dia, busca os exercícios associados e as cargas planeadas
        days_with_exercises = []
        for day in days:
            day_exercises = session.exec(
                select(PlanDayExercise)
                .where(PlanDayExercise.plan_day_id == day.id)
                .order_by(PlanDayExercise.order_index)
            ).all()

            exercises_details = []
            for day_exercise in day_exercises:
                # Busca os detalhes do exercício
                exercise = session.get(Exercise, day_exercise.exercise_id)
                
                # Busca as cargas planeadas para este exercício
                sets_loads = session.exec(
                    select(PlanExerciseSetLoad)
                    .where(PlanExerciseSetLoad.plan_day_exercise_id == day_exercise.id)
                    .order_by(PlanExerciseSetLoad.set_number)
                ).all()

                exercises_details.append({
                    "id": day_exercise.id,
                    "exercise_id": day_exercise.exercise_id,
                    "exercise_name": exercise.name if exercise else "Exercício removido",
                    "exercise_muscles": exercise.muscles if exercise else None,
                    "exercise_url": exercise.url if exercise else None,
                    "order_index": day_exercise.order_index,
                    "sets": day_exercise.sets,
                    "reps_range": day_exercise.reps_range,
                    "rest_range_seconds": day_exercise.rest_range_seconds,
                    "tempo": day_exercise.tempo,
                    "is_superset_group": day_exercise.is_superset_group,
                    "substitution_allowed": day_exercise.substitution_allowed,
                    "sets_loads": [
                        {
                            "set_number": sl.set_number,
                            "load_kg": sl.load_kg,
                        }
                        for sl in sets_loads
                    ],
                })
            
            days_with_exercises.append({
                "id": day.id,
                "name": day.name,
                "order_index": day.order_index,
                "notes": day.notes,
                "exercises": exercises_details,
            })

        return {
            "active_plan": {
                "id": active_plan.id,
                "active_from": str(active_plan.active_from),
            },
            "plan": {
                "id": plan.id,
                "name": plan.name,
                "status": plan.status,
                "start_date": str(plan.start_date) if plan.start_date else None,
                "end_date": str(plan.end_date) if plan.end_date else None,
                "notes": plan.notes,
            },
            "days": days_with_exercises,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter plano de treino: {e}")
    
# ==================================================
# GET /portal/my-meal-plans
# ==================================================

@router.get("/my-meal-plans")
async def get_my_meal_plans(
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> list:
    # Devolve os planos alimentares ativos do cliente autenticado, com todas as refeições e detalhes.

    try:
        client_id = _get_client_id(current_user)
        # Reutiliza o CRUD de nutrição para obter os planos alimentares ativos do cliente
        meal_plans = nutrition_crud.list_meal_plans_by_client(session, client_id, include_archived=False)

        return [nutrition_crud.build_meal_plan_read(session, mp) for mp in meal_plans]
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter planos alimentares: {e}")
    
# ==================================================
# GET /portal/my-check-ins
# ==================================================

@router.get("/my-check-ins", response_model=List[CheckInRead])
async def get_my_check_ins(
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> List[CheckInRead]:
    # Devolve todos os check-ins do cliente autenticado, ordenados do mais recente para o mais antigo.
    # Inclui pendentes, completados e ignorados.

    try:
        client_id =_get_client_id(current_user)

        checkins = session.exec(
            select(CheckIn)
            .where(CheckIn.client_id == client_id)
            .order_by(CheckIn.created_at.desc())
        ).all()

        return [CheckInRead.model_validate(ci) for ci in checkins]
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter check-ins: {e}")
    
# ==================================================
# POST /portal/check-ins/{checkin_id}/respond
# ==================================================

@router.post("/check-ins/{checkin_id}/respond", response_model=CheckInRead)
async def respond_to_check_in(
    checkin_id: str,
    payload: CheckInResponse,
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> CheckInRead:
    # O cliente responde a um check-in pendente. Valida que o check-in pertence ao cliente autenticado
    # antes de aceitar a resposta - um cliente não pode responder a check-ins de outros clientes.

    try:
        client_id = _get_client_id(current_user)

        checkin = session.get(CheckIn, checkin_id)
        if not checkin:
            raise HTTPException(status_code=404, detail="Check-in não encontrado.")
        
        # Verifica ownership — check-in tem que pertencer ao cliente autenticado
        if checkin.client_id != client_id:
            raise HTTPException(status_code=403, detail="Não autorizado a responder a este check-in.")
        
        if checkin.status == "completed":
            raise HTTPException(status_code=400, detail="Check-in já foi respondido.")
        
        if checkin.status == "skipped":
            raise HTTPException(status_code=400, detail="Check-in foi ignorado pelo Personal Trainer e não pode ser respondido.")
        
        # Aplica os dados da resposta do cliente
        checkin.weight_kg = payload.weight_kg
        checkin.body_fat = payload.body_fat
        checkin.client_notes = payload.client_notes

        if payload.questionnaire:
            checkin.questionnaire = payload.questionnaire.model_dump(exclude_none=True)

        if payload.photos:
            checkin.photos = {"photos": [p.model_dump() for p in payload.photos]}

        checkin.status = "completed"
        checkin.completed_at = datetime.now(timezone.utc)

        session.add(checkin)
        commit_or_rollback(session)
        session.refresh(checkin)

        return CheckInRead.model_validate(checkin)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao responder ao check-in: {e}")
    
# ==================================================
# GET /portal/my-supplements  
# ==================================================

@router.get("/my-supplements", response_model=List[ClientSupplementPublic])
async def get_my_supplements(
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> List[ClientSupplementPublic]:
    # Devolve a lista de suplementos atribuídos ao cliente autenticado, com detalhes do suplemento do catálogo.
    # Usa o schema ClientSupplementPublic para omitir as notas específicas do Personal Trainer.

    try:
        client_id = _get_client_id(current_user)

        assignments = session.exec(
            select(ClientSupplement)
            .where(ClientSupplement.client_id == client_id)
        ).all()

        supplements_public = []
        for assignment in assignments:
            supplement = session.get(Supplement, assignment.supplement_id)
            if not supplement or supplement.archived_at is not None:
                # Suplemento arquivado ou removido - omite da lista do cliente
                continue


            supplements_public.append(ClientSupplementPublic(
                id=assignment.id,
                supplement_id=assignment.supplement_id,
                dose=assignment.dose,
                timing_notes=assignment.timing_notes,
                notes=assignment.notes,
                assigned_at=assignment.assigned_at,
                supplement_name=supplement.name,
                supplement_description=supplement.description,
                supplement_serving_size=supplement.serving_size,
                supplement_timing=supplement.timing,
            ))

        return supplements_public
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter suplementos: {e}")