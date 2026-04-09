"""
Router do portal do cliente — endpoints exclusivos para `role="client"`.

Responsabilidade desta camada:
    - autenticar e autorizar o cliente via JWT
    - orquestrar chamadas ao domínio/modelos
    - devolver payloads prontos para consumo pelo frontend

Regra central:
    - o cliente é sempre resolvido a partir de `current_user.client_id`
      e nunca a partir de IDs enviados manualmente pelo frontend

Endpoints principais:
    GET /portal/branding
    GET /portal/my-profile
    PATCH /portal/my-profile
    GET /portal/my-plan
    PUT /portal/my-plan/exercises/{plan_day_exercise_id}/set_logs
    GET /portal/my-meal-plans
    GET /portal/my-check-ins
    POST /portal/check-ins/{id}/respond
    GET /portal/my-supplements
"""
import logging
from datetime import datetime, timezone, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

import app.crud.nutrition as nutrition_crud
from app.api.deps import db_session
from app.core.security import require_client
from app.core.db_errors import commit_or_rollback
from app.db.models.client import Client
from app.db.models.trainer_settings import TrainerSettings
from app.db.models.user import User
from app.db.models.training import (
    TrainingPlan,
    TrainingPlanDay,
    PlanDayExercise,
    PlanExerciseSetLoad,
    ClientActivePlan,
    Exercise,
    ClientExerciseSetLog,
)
from app.db.models.client_supplement import ClientSupplement
from app.db.models.supplement import Supplement
from app.schemas.client_supplement import ClientSupplementPublic
from app.schemas.client_portal import (
    PortalBrandingRead,
    ClientPortalProfileRead,
    ClientPortalProfileUpdate,
)
from app.db.models.checkin import CheckIn
from app.schemas.checkin import CheckInResponse, CheckInRead
from app.schemas.training import (
    ClientExerciseSetLogRead,
    ClientExerciseSetLogUpsertRequest,
)
from app.utils.time import utc_now


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portal", tags=["Client Portal"])

# ----------------------------------
# Helpers de aplicação:
# centralizam regras de acesso e transformação para evitar duplicação nos endpoints.
# ----------------------------------

def _get_client_id(current_user) -> str:
    """
    Resolve o `client_id` a partir do utilizador autenticado.
    Falha com 403 quando o JWT é válido mas não está associado a um perfil de cliente.
    """
    if not current_user.client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta de cliente sem perfil associado. Contacta o teu treinador."
        )
    return current_user.client_id

def _get_client_or_404(session: Session, current_user: User) -> Client:
    """
    Carrega o agregado `Client` correspondente ao utilizador autenticado.
    Lança 404 quando o JWT aponta para um client_id inexistente na base de dados.
    """
    client = session.get(Client, _get_client_id(current_user))
    if not client:
        raise HTTPException(status_code=404, detail="Perfil de cliente não encontrado.")
    return client

def _get_active_client_plan(session: Session, client_id: str) -> ClientActivePlan | None:
    """
    Busca o plano de treino ativo do cliente.
    Isola a regra de que um plano ativo é o registo com `active_to IS NULL`.
    """
    return session.exec(
        select(ClientActivePlan)
        .where(
            ClientActivePlan.client_id == client_id,
            ClientActivePlan.active_to == None
        )
    ).first()

def _get_day_exercise_for_active_plan_or_404(
    session: Session, 
    client_id: str, 
    plan_day_exercise_id: str
) -> PlanDayExercise:
    """
    Resolve um exercício do plano e valida o boundary de acesso do cliente.

    Esta função garante que o cliente só pode interagir com exercícios que
    pertencem ao seu plano atualmente ativo, mesmo que conheça IDs válidos de
    outros contextos.
    """
    
    active_plan = _get_active_client_plan(session, client_id)
    if not active_plan:
        raise HTTPException(status_code=404, detail="Nenhum plano de treino ativo encontrado para o cliente.")

    day_exercise = session.get(PlanDayExercise, plan_day_exercise_id)
    if not day_exercise:
        raise HTTPException(status_code=404, detail="Exercício do plano não encontrado.")
    
    plan_day = session.get(TrainingPlanDay, day_exercise.plan_day_id)
    if not plan_day or plan_day.plan_id != active_plan.training_plan_id:
        raise HTTPException(status_code=404, detail="Exercício não pertence ao plano ativo do cliente.")
    
    return day_exercise

def _client_set_log_to_read(
    row: ClientExerciseSetLog,
    day_exercise: PlanDayExercise,
    exercise: Exercise | None,
) -> ClientExerciseSetLogRead:
    """
    Mapeia o model ORM para o contrato público de resposta dos logs.
    Mantém a tradução concentrada num único ponto para reduzir drift entre rotas.
    """
    return ClientExerciseSetLogRead(
        id=row.id,
        client_id=row.client_id,
        plan_day_exercise_id=row.plan_day_exercise_id,
        exercise_id=day_exercise.exercise_id,
        exercise_name=exercise.name if exercise else "Exercício removido",
        set_number=row.set_number,
        weight_kg=row.weight_kg,
        reps_done=row.reps_done,
        notes=row.notes,
        logged_at=row.logged_at,
        updated_at=row.updated_at,
    )

# ==================================================
# GET /portal/branding
# ==================================================
@router.get("/branding", response_model=PortalBrandingRead, status_code=status.HTTP_200_OK)
async def get_portal_branding(
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> PortalBrandingRead:
    """
    Devolve o branding efetivo do portal do cliente.

    A resposta combina:
    - dados de identidade visual guardados em `trainer_settings`
    - o `logo_url` guardado no `User` do trainer
    """

    # Resolver o cliente autenticado antes de procurar o respetivo trainer.
    client = _get_client_or_404(session, current_user)
    
    # Sem trainer associado não existe contexto de branding a devolver.
    if not client.owner_trainer_id:
        raise HTTPException(status_code=404, detail="Personal Trainer não associado ao cliente.")
    
    # O logo continua no model User; as restantes preferências estão em TrainerSettings.
    trainer = session.get(User, client.owner_trainer_id)

    # Lookup simples sem lógica de domínio adicional: só queremos materializar o branding.
    trainer_settings = session.exec(
        select(TrainerSettings).where(
            TrainerSettings.trainer_user_id == client.owner_trainer_id
        )
    ).first()

    # O DTO final protege o frontend de saber onde cada campo é persistido.
    return PortalBrandingRead(
        app_name=trainer_settings.app_name if trainer_settings else None,
        logo_url=trainer.logo_url if trainer else None,
        primary_color=trainer_settings.primary_color if trainer_settings else None,
        body_color=trainer_settings.body_color if trainer_settings else None,
    )


def _client_to_portal_profile_read(client: Client) -> ClientPortalProfileRead:
    """
    Mapeia o agregado Client para o contrato público do perfil do portal.
    """
    return ClientPortalProfileRead(
        id=client.id,
        full_name=client.full_name,
        email=client.email,
        phone=client.phone,
        birth_date=client.birth_date,
        sex=client.sex,
        height_cm=client.height_cm,
        training_modality=client.training_modality,
        objective=client.objetive,
        notes=client.notes,
        emergency_contact_name=client.emergency_contact_name,
        emergency_contact_phone=client.emergency_contact_phone,
    )

# ==================================================
# GET /portal/my-profile
# ==================================================

@router.get("/my-profile", response_model=ClientPortalProfileRead)
async def get_my_profile(
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> ClientPortalProfileRead:
    # Endpoint de leitura simples do perfil autenticado.
    # Mantém a transformação local para devolver apenas campos consumidos pelo portal.

    try:
        client = _get_client_or_404(session, current_user)

        return _client_to_portal_profile_read(client)
    
    except HTTPException:
        raise

    except Exception:
        logger.exception("Erro inesperado ao obter perfil do cliente %s", current_user.id)
        raise HTTPException(status_code=500, detail="Erro ao obter perfil do cliente.")

# ==================================================
# PATCH /portal/my-profile
# ==================================================

@router.patch("/my-profile", response_model=ClientPortalProfileRead, status_code=status.HTTP_200_OK)
async def update_my_profile(
    payload: ClientPortalProfileUpdate,
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> ClientPortalProfileRead:
    """
    Atualiza os dados editáveis do perfil do cliente autenticado.

    O cliente é sempre resolvido via JWT e nunca por identificadores enviados pelo frontend.
    """
    try:
        client = _get_client_or_404(session, current_user)
        data = payload.model_dump(exclude_unset=True)

        if "email" in data and data["email"] is not None:
            data["email"] = str(data["email"]).strip()

        if "full_name" in data and data["full_name"] is not None:
            data["full_name"] = data["full_name"].strip()

        if "phone" in data and data["phone"] is not None:
            data["phone"] = data["phone"].strip()

        if "notes" in data and data["notes"] is not None:
            data["notes"] = data["notes"].strip() or None

        if "emergency_contact_name" in data and data["emergency_contact_name"] is not None:
            data["emergency_contact_name"] = data["emergency_contact_name"].strip() or None

        if "emergency_contact_phone" in data and data["emergency_contact_phone"] is not None:
            data["emergency_contact_phone"] = data["emergency_contact_phone"].strip() or None

        if "phone" in data and data["phone"] != client.phone:
            existing_phone = session.exec(
                select(Client).where(Client.phone == data["phone"])
            ).first()
            if existing_phone and existing_phone.id != client.id:
                raise HTTPException(status_code=409, detail="Telefone já existe.")

        if "email" in data and data["email"] != client.email and data["email"] is not None:
            existing_email = session.exec(
                select(Client).where(Client.email == data["email"])
            ).first()
            if existing_email and existing_email.id != client.id:
                raise HTTPException(status_code=409, detail="Email já existe.")

        for key, value in data.items():
            setattr(client, key, value)

        client.updated_at = utc_now()
        session.add(client)
        commit_or_rollback(session)
        session.refresh(client)

        return _client_to_portal_profile_read(client)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Erro inesperado ao atualizar perfil do cliente %s", current_user.id)
        raise HTTPException(status_code=500, detail="Erro ao atualizar perfil do cliente.")
    
# ==================================================
# GET /portal/my-plan
# ==================================================

@router.get("/my-plan")
async def get_my_training_plan(
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> dict:
    # Orquestra a montagem do plano ativo para o portal:
    # cabeçalho do plano, dias, exercícios, cargas planeadas e logs reais do cliente.

    try:
        client_id = _get_client_id(current_user)

        # A ausência de plano ativo não é erro de domínio para o portal.
        active_plan = session.exec(
            select(ClientActivePlan)
            .where(
                ClientActivePlan.client_id == client_id,
                ClientActivePlan.active_to == None
            )
        ).first()

        if not active_plan:
            return {"active_plan": None, "plan": None, "days": []}
        
        # Proteção defensiva: se o mapeamento ativo apontar para um plano removido,
        # devolvemos estrutura vazia em vez de explodir no frontend.
        plan = session.get(TrainingPlan, active_plan.training_plan_id)
        if not plan:
            return {"active_plan": None, "plan": None, "days": []}
        
        # O portal precisa da ordem natural de execução dos dias.
        days = session.exec(
            select(TrainingPlanDay)
            .where(TrainingPlanDay.plan_id == plan.id)
            .order_by(TrainingPlanDay.order_index)
        ).all()

        # Montagem manual do payload para manter o contrato do portal estável
        # sem expor diretamente relações ORM.
        days_with_exercises = []
        for day in days:
            day_exercises = session.exec(
                select(PlanDayExercise)
                .where(PlanDayExercise.plan_day_id == day.id)
                .order_by(PlanDayExercise.order_index)
            ).all()

            exercises_details = []
            for day_exercise in day_exercises:
                # O exercício pode ter sido removido do catálogo; o portal continua
                # a mostrar o registo histórico do plano com fallback textual.
                exercise = session.get(Exercise, day_exercise.exercise_id)
                
                # Cargas planeadas por série para comparação com execução real.
                sets_loads = session.exec(
                    select(PlanExerciseSetLoad)
                    .where(PlanExerciseSetLoad.plan_day_exercise_id == day_exercise.id)
                    .order_by(PlanExerciseSetLoad.set_number)
                ).all()

                # Logs reais executados pelo cliente no contexto deste exercício do plano.
                client_logs_row = session.exec(
                    select(ClientExerciseSetLog)
                    .where(
                        ClientExerciseSetLog.client_id == client_id,
                        ClientExerciseSetLog.plan_day_exercise_id == day_exercise.id,
                    )
                    .order_by(ClientExerciseSetLog.set_number)
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
                    "notes": day_exercise.notes,
                    "sets_loads": [
                        {
                            "set_number": sl.set_number,
                            "planned_weight_kg": sl.load_kg,
                        }
                        for sl in sets_loads
                    ],

                    "client_set_logs": [
                        {
                            "id": row.id,
                            "client_id": row.client_id,
                            "plan_day_exercise_id": row.plan_day_exercise_id,
                            "exercise_id": day_exercise.exercise_id,
                            "exercise_name": exercise.name if exercise else "Exercício removido",
                            "set_number": row.set_number,
                            "weight_kg": row.weight_kg,
                            "reps_done": row.reps_done,
                            "notes": row.notes,
                            "logged_at": row.logged_at.isoformat(),
                            "updated_at": row.updated_at.isoformat(),
                        }
                        for row in client_logs_row
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
    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Erro inesperado ao obter plano de treino para o cliente %s", current_user.id)
        raise HTTPException(status_code=500, detail="Erro ao obter plano de treino.")
    
@router.put("/my-plan/exercises/{plan_day_exercise_id}/set_logs", response_model=List[ClientExerciseSetLogRead])
async def upsert_exercise_set_logs(
    plan_day_exercise_id: str,
    payload: ClientExerciseSetLogUpsertRequest,
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> List[ClientExerciseSetLogRead]:
    """
    Substitui os logs reais de execução por série para um exercício do plano ativo.

    O payload passa a ser a fonte de verdade por combinação de:
    - cliente autenticado
    - exercício do plano ativo
    - número da série
    """

    try:

        # Primeiro validamos o boundary de acesso; só depois aceitamos escrita.
        client_id = _get_client_id(current_user)
        day_exercise = _get_day_exercise_for_active_plan_or_404(
            session, 
            client_id, 
            plan_day_exercise_id
        )

        # Duplicados no payload seriam ambíguos mesmo antes de chegar à constraint da BD.
        seen_set_numbers = set()

        for item in payload.logs:
            # Regra de negócio: só aceitamos logs para séries previstas no plano.
            if item.set_number > day_exercise.sets:
                raise HTTPException(
                    status_code=400, 
                    detail=(
                        f"A série {item.set_number} excede o número de séries "
                        "definido para este exercício."
                    ),
                )
            
            if item.set_number in seen_set_numbers:
                raise HTTPException(
                    status_code=400, 
                    detail=f"A série {item.set_number} foi enviada mais do que uma vez."
                )
            seen_set_numbers.add(item.set_number)

            notes = item.notes.strip() if item.notes else None
            # Cada série tem de transportar pelo menos um sinal útil de execução.
            if item.weight_kg is None and item.reps_done is None and notes is None:
                raise HTTPException(
                    status_code=400, 
                    detail=(
                            f"A série {item.set_number} precisa de pelo menos um valor "
                            "entre carga, repetições ou notas."
                        ),
                )  

            # Upsert por chave natural do domínio: cliente + exercício do plano + série.
            existing_log = session.exec(
                select(ClientExerciseSetLog)
                .where(
                    ClientExerciseSetLog.client_id == client_id,
                    ClientExerciseSetLog.plan_day_exercise_id == plan_day_exercise_id,
                    ClientExerciseSetLog.set_number == item.set_number,
                )
            ).first()

            if existing_log:
                # Atualização parcial do registo existente, preservando o `logged_at` original.
                existing_log.weight_kg = item.weight_kg
                existing_log.reps_done = item.reps_done
                existing_log.notes = notes
                existing_log.updated_at = utc_now()
                session.add(existing_log)
            else:
                # Em criação, `logged_at` e `updated_at` são preenchidos pelo model.
                row = ClientExerciseSetLog(
                    client_id=client_id,
                    plan_day_exercise_id=plan_day_exercise_id,
                    set_number=item.set_number,
                    weight_kg=item.weight_kg,
                    reps_done=item.reps_done,
                    notes=notes,
                )
                session.add(row)

        # Remover logs antigos que já não fazem parte do estado enviado pelo frontend.
        existing_rows = session.exec(
            select(ClientExerciseSetLog)
            .where(
                ClientExerciseSetLog.client_id == client_id,
                ClientExerciseSetLog.plan_day_exercise_id == plan_day_exercise_id,
            )
        ).all()

        for row in existing_rows:
            if row.set_number not in seen_set_numbers:
                session.delete(row)

        commit_or_rollback(session)

        # Lemos novamente após commit para devolver o estado persistido final.
        if not seen_set_numbers:
            return []

        persisted_rows = session.exec(
            select(ClientExerciseSetLog)
            .where(
                ClientExerciseSetLog.client_id == client_id,
                ClientExerciseSetLog.plan_day_exercise_id == plan_day_exercise_id,
                ClientExerciseSetLog.set_number.in_(seen_set_numbers),
            )
            .order_by(ClientExerciseSetLog.set_number)
        ).all()

        exercise = session.get(Exercise, day_exercise.exercise_id)

        return [
            _client_set_log_to_read(row, day_exercise, exercise)
            for row in persisted_rows
        ]  
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Erro inesperado ao upsertar logs de séries para o cliente %s, exercício %s: %s", 
            current_user.id, 
            plan_day_exercise_id,
            str(e)
        )
        raise HTTPException(status_code=500, detail="Erro ao registar logs de séries.")
# ==================================================
# GET /portal/my-meal-plans
# ==================================================

@router.get("/my-meal-plans")
async def get_my_meal_plans(
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> list:
    # Delegamos a regra de negócio de nutrição ao módulo CRUD para manter este router fino.

    try:
        client_id = _get_client_id(current_user)
        # O portal apenas orquestra e devolve o formato já construído pelo módulo de nutrição.
        meal_plans = nutrition_crud.list_meal_plans_by_client(
            session, 
            client_id, 
            include_archived=False
        )

        return [nutrition_crud.build_meal_plan_read(session, mp) for mp in meal_plans]
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.exception("Erro inesperado ao obter planos alimentares para o cliente %s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Erro ao obter planos alimentares.")
    
# ==================================================
# GET /portal/my-check-ins
# ==================================================

@router.get("/my-check-ins", response_model=List[CheckInRead])
async def get_my_check_ins(
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> List[CheckInRead]:
    # Endpoint de leitura direta do histórico de check-ins do cliente.
    # A ordenação descendente favorece o caso de uso principal do portal.

    try:
        client_id =_get_client_id(current_user)

        checkins = session.exec(
            select(CheckIn)
            .where(CheckIn.client_id == client_id)
            .order_by(CheckIn.created_at.desc())
        ).all()

        return [CheckInRead.model_validate(ci) for ci in checkins]
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.exception("Erro inesperado ao obter check-ins para o cliente %s: %s", current_user.id, str(e))
        raise HTTPException(status_code=500, detail="Erro ao obter check-ins.")
    
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
    # Caso de uso de resposta a check-in.
    # O endpoint valida ownership e estado antes de aplicar a resposta do cliente.

    try:
        client_id = _get_client_id(current_user)

        checkin = session.get(CheckIn, checkin_id)
        if not checkin:
            raise HTTPException(status_code=404, detail="Check-in não encontrado.")
        
        # Boundary de segurança: um cliente só pode responder aos seus próprios check-ins.
        if checkin.client_id != client_id:
            raise HTTPException(status_code=403, detail="Não autorizado a responder a este check-in.")
        
        if checkin.status == "completed":
            raise HTTPException(status_code=400, detail="Check-in já foi respondido.")
        
        if checkin.status == "skipped":
            raise HTTPException(status_code=400, detail="Check-in foi ignorado pelo Personal Trainer e não pode ser respondido.")
        
        # Aplicar a resposta é a única mutação permitida neste endpoint.
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
        logger.exception("Erro inesperado ao responder ao check-in para o cliente %s, check-in %s: %s", 
                         current_user.id,
                         checkin_id,
                         str(e))
        raise HTTPException(status_code=500, detail="Erro ao responder ao check-in.")
    
# ==================================================
# GET /portal/my-supplements  
# ==================================================

@router.get("/my-supplements", response_model=List[ClientSupplementPublic])
async def get_my_supplements(
    session: Session = Depends(db_session),
    current_user = Depends(require_client),
) -> List[ClientSupplementPublic]:
    # Lista os suplementos visíveis para o cliente, já enriquecidos com dados do catálogo.
    # O schema público evita expor detalhes internos desnecessários ao portal.

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
                # Se o suplemento já não estiver disponível no catálogo, omitimos da vista do cliente.
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
    
    except HTTPException:
        raise

    except Exception:
        logger.exception("Erro inesperado ao obter suplementos para o cliente %s", current_user.id)
        raise HTTPException(status_code=500, detail="Erro ao obter suplementos.")
