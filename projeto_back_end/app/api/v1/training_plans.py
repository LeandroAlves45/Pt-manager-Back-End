from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from typing import List, Optional
from uuid import UUID

from app.api.deps import db_session
from app.core.db_errors import commit_or_rollback
from app.db.models.client import Client
from app.db.models.training import (TrainingPlan, TrainingPlanDay, PlanDayExercise, PlanExerciseSetLoad, ClientActivePlan, Exercise,)
from app.schemas.training import (TrainingPlanCreate, TrainingPlanRead, TrainingPlanUpdate, TrainingPlanDayCreate, TrainingPlanDayRead, TrainingPlanDayUpdate,
    PlanDayExerciseCreate, PlanDayExerciseRead, PlanDayExerciseUpdate, PlanExerciseSetLoadCreate, PlanExerciseSetLoadRead, PlanExerciseSetLoadUpdate, ClientActivePlanCreate,
    ClientActivePlanRead, ClonePlanToClientCreate)
from app.utils.time import utc_now

router = APIRouter(prefix="/training_plans", tags=["Training Plans"])

#======================
#Helpers
#======================

#função de resposta, converte model Bd em schema
def _plan_to_read(p: TrainingPlan) -> TrainingPlanRead:
    return TrainingPlanRead(
        id=p.id,
        name=p.name,
        client_id=p.client_id,
        status=p.status,
        start_date=p.start_date,
        end_date=p.end_date,
        notes=p.notes,
        created_at=p.created_at,
        updated_at=p.updated_at
    )

def day_to_read(d: TrainingPlanDay) -> TrainingPlanDayRead:
    return TrainingPlanDayRead(
        id=d.id,
        plan_id=d.plan_id,
        name=d.name,
        order_index=d.order_index,
        notes=d.notes,
        created_at=d.created_at,
        updated_at=d.updated_at
    )

def _day_exercise_to_read(de: PlanDayExercise, session: Session) -> PlanDayExerciseRead:

    # ✅ Buscar exercício na base de dados
    exercise = session.get(Exercise, de.exercise_id)
    
    # Validação de segurança (caso o exercício tenha sido apagado)
    if not exercise:
        raise HTTPException(
            status_code=500,
            detail=f"Exercício {de.exercise_id} não encontrado na base de dados."
        )
    return PlanDayExerciseRead(
        id=de.id,
        plan_day_id=de.plan_day_id,
        exercise_id=de.exercise_id,
        exercise_name=exercise.name,
        exercise_muscles=exercise.muscles,
        exercise_url=exercise.url,
        order_index=de.order_index,
        sets=de.sets,
        reps_range=de.reps_range,
        rest_range_seconds=de.rest_range_seconds,
        tempo=de.tempo,
        is_superset_group=de.is_superset_group,
        substitution_allowed=de.substitution_allowed,
        created_at=de.created_at,
        updated_at=de.updated_at
    )

#função de resposta para create e update de set load
def _set_load_to_read(
    sl: PlanExerciseSetLoad,
    session: Session
) -> PlanExerciseSetLoadRead:
    """
    Converte PlanExerciseSetLoad em schema de resposta.
    Busca automaticamente os detalhes do exercício.
    
    Args:
        sl: Set load do exercício
        session: Sessão do SQLAlchemy para buscar dados
    
    Returns:
        Schema de resposta com todos os campos
    """
    # Buscar o PlanDayExercise para obter o exercise_id
    day_exercise = session.get(PlanDayExercise, sl.plan_day_exercise_id)
    
    if not day_exercise:
        raise HTTPException(
            status_code=500,
            detail=f"Exercício do dia {sl.plan_day_exercise_id} não encontrado."
        )
    
    # Buscar o Exercise para obter nome e músculos
    exercise = session.get(Exercise, day_exercise.exercise_id)
    
    if not exercise:
        raise HTTPException(
            status_code=500,
            detail=f"Exercício {day_exercise.exercise_id} não encontrado."
        )
    
    return PlanExerciseSetLoadRead(
        # Campos do PlanExerciseSetLoad
        id=sl.id,
        plan_day_exercise_id=sl.plan_day_exercise_id,
        exercise_id=exercise.id,
        exercise_name=exercise.name,
        exercise_muscles=exercise.muscles,
        set_number=sl.set_number,
        load_kg=sl.load_kg,
        notes=sl.notes,
        created_at=sl.created_at,
        updated_at=sl.updated_at,
    )

#função de resposta para get de set loads
def _set_load_with_details_to_read(
    sl: PlanExerciseSetLoad,
    day_exercise: PlanDayExercise,
    exercise: Exercise
) -> PlanExerciseSetLoadRead:
    """
    Converte set load com dados já carregados (evita queries extras).
    Usa-se quando já fizemos JOIN.
    """
    return PlanExerciseSetLoadRead(
        id=sl.id,
        plan_day_exercise_id=sl.plan_day_exercise_id,
        set_number=sl.set_number,
        load_kg=sl.load_kg,
        notes=sl.notes,
        created_at=sl.created_at,
        updated_at=sl.updated_at,
        exercise_id=exercise.id,
        exercise_name=exercise.name,
        exercise_muscles=exercise.muscles
    )

#função de resposta para get de plano ativo do cliente, com detalhes do cliente e plano
def _active_to_read(
    cap: ClientActivePlan,
    session: Session
) -> ClientActivePlanRead:
    """
    Converte ClientActivePlan em schema de resposta.
    Busca automaticamente os detalhes do cliente e do plano.
    
    Args:
        cap: Client active plan
        session: Sessão do SQLAlchemy para buscar dados
    
    Returns:
        Schema de resposta com todos os campos
    """
    # Buscar cliente
    client = session.get(Client, cap.client_id)
    if not client:
        raise HTTPException(
            status_code=500,
            detail=f"Cliente {cap.client_id} não encontrado."
        )
    
    # Buscar plano de treino
    plan = session.get(TrainingPlan, cap.training_plan_id)
    if not plan:
        raise HTTPException(
            status_code=500,
            detail=f"Plano de treino {cap.training_plan_id} não encontrado."
        )
    
    return ClientActivePlanRead(
        # Campos do ClientActivePlan
        id=cap.id,
        client_id=cap.client_id,
        client_full_name=client.full_name,
        training_plan_id=cap.training_plan_id,
        training_plan_name=plan.name,
        active_from=cap.active_from,
        active_to=cap.active_to,
        created_at=cap.created_at,
        updated_at=cap.updated_at
    )

#======================
#CRUD Training plans
#======================

#get todos os planos de treino
@router.get("/", response_model=List[TrainingPlanRead])
async def list_plans(
    session: Session = Depends(db_session),
    Client_id: Optional[str] = Query(default=None),
    Plan_id: Optional[str] = Query(default=None),
    Status: Optional[str] = Query(default=None, alias="status"),
    Page_size: Optional[int] = Query(default=None, ge=1, le=1000),
    Page_number: Optional[int] = Query(default=None, ge=1),
) -> List[TrainingPlanRead]:
    #lista de planos de treino com filtros simples
    stmt = select(TrainingPlan)

    if Client_id is not None:
        stmt = stmt.where(TrainingPlan.client_id == Client_id.strip())

    if Plan_id is not None:
        stmt = stmt.where(TrainingPlan.id == Plan_id.strip())

    if Status is not None:
        stmt = stmt.where(TrainingPlan.status == Status.strip())
    
    #paginação
    if (Page_size is None) ^ (Page_number is None):
        raise HTTPException(status_code=400, detail="Page_size e Page_number devem ser fornecidos juntos para paginação.")
    if Page_size is not None and Page_number is not None:
        if Page_size <= 0 or Page_number <= 0:
            raise HTTPException(status_code=400, detail="Page_size e Page_number devem ser maiores que zero.")
        offset = (Page_number - 1) * Page_size
        stmt = stmt.offset(offset).limit(Page_size)
    
    try:
        rows = session.exec(stmt).all()

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao listar os planos de treino.") from e
    
    return [_plan_to_read(r) for r in rows]

#criação de novo plano de treino
@router.post("/", response_model=TrainingPlanRead, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: TrainingPlanCreate,
    session: Session = Depends(db_session)
) -> TrainingPlanRead:
    #cria novo plano de treino
    try:

        #normalizar e validar client_id se fornecido
        client_id_normalized = payload.client_id.strip() if payload.client_id else None

        if client_id_normalized:
            client = session.exec(
                select(Client).where(Client.id == client_id_normalized)
            ).first()

            if not client:
                raise HTTPException(status_code=404, detail="Cliente não encontrado.")
            
            if client.archived_at is not None:
                raise HTTPException(status_code=400, detail="Não é possível atribuir um plano de treino a um cliente arquivado.")
        
        plan = TrainingPlan(
            client_id=client_id_normalized,
            name=payload.name.strip(),
            status=payload.status.strip() if payload.status else "draft",
            start_date=payload.start_date,
            end_date=payload.end_date,
            notes=payload.notes
        )

        session.add(plan)
        commit_or_rollback(session)
        session.refresh(plan)
        return _plan_to_read(plan)

    except IntegrityError as e:
        raise HTTPException(status_code=400, detail="Erro de integridade ao criar o plano de treino.") from e
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao criar o plano de treino.") from e

#atualizar plano de treino
@router.put("/{plan_id}", response_model=TrainingPlanRead)
async def update_plan(
    plan_id: str,
    payload: TrainingPlanUpdate,
    session: Session = Depends(db_session)
) -> TrainingPlanRead:
    
    #atualiza plano de treino existente
    try:
        plan = session.get(TrainingPlan, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plano de treino não encontrado.")

        if payload.client_id is not None:
            if payload.client_id:
                client = session.exec(
                    select(Client).where(Client.id == payload.client_id.strip())
                ).first()
                if not client:
                    raise HTTPException(status_code=404, detail="Cliente não encontrado.")
                if client.archived_at is not None:
                    raise HTTPException(status_code=400, detail="Não é possível atribuir um plano de treino a um cliente arquivado.")
            plan.client_id = payload.client_id

        #atualiza campos se fornecidos
        if payload.name is not None:
            plan.name = payload.name.strip()
        if payload.status is not None:
            plan.status = payload.status.strip()
        if payload.start_date is not None:
            plan.start_date = payload.start_date
        if payload.end_date is not None:
            plan.end_date = payload.end_date
        if payload.notes is not None:
            plan.notes = payload.notes

        plan.updated_at = utc_now()

        session.add(plan)
        commit_or_rollback(session)
        session.refresh(plan)
        return _plan_to_read(plan)
    
    except IntegrityError as e:
        raise HTTPException(status_code=400, detail="Erro de integridade ao atualizar o plano de treino.") from e
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao atualizar o plano de treino.") from e

#deletar plano de treino
@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: str,
    session: Session = Depends(db_session)
) -> None:
    try:
        plan = session.get(TrainingPlan, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plano de treino não encontrado.")
        
        #Delete em cascade nao existe automaticamente em sqlmodel/sqlite
        #Delete manual para nao deixar registos orfãos
        days = session.exec(select(TrainingPlanDay).where(TrainingPlanDay.plan_id == plan.id)).all()
        for day in days:
            day_ex = session.exec(select(PlanDayExercise).where(PlanDayExercise.plan_day_id == day.id)).all()
            for x in day_ex:
                loads = session.exec(select(PlanExerciseSetLoad).where(PlanExerciseSetLoad.plan_day_exercise_id == x.id)).all()
                for l in loads:
                    session.delete(l)
                session.delete(x)
            session.delete(day)
        
        #remove mapeamentos de plano de treino (histórico)
        actives = session.exec(select(ClientActivePlan).where(ClientActivePlan.training_plan_id == plan.id)).all()
        for active in actives:
            session.delete(active)

        session.delete(plan)
        commit_or_rollback(session)
        return None
    
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao deletar o plano de treino.") from e

#===================
#CRUD: Days dentro de um Plan
#===================

#get de planos de treino dias
@router.get("/{plan_id}/days", response_model=List[TrainingPlanDayRead])
async def list_plan_days(plan_id: str, session: Session = Depends(db_session),) -> List[TrainingPlanDayRead]:

    #lista os dias de um plano de treino
    try:
        plan = session.get(TrainingPlan, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plano de treino nao encontrado.")

        days = session.exec(
            select(TrainingPlanDay)
            .where(TrainingPlanDay.plan_id == plan_id)
            .order_by(TrainingPlanDay.order_index.asc(), TrainingPlanDay.created_at.asc())
        ).all()

        return [day_to_read(d) for d in days]

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao listar os dias do plano de treino.") from e
    
#criar novo dia no plano de treino
@router.post("/{plan_id}/days", response_model=TrainingPlanDayRead, status_code=status.HTTP_201_CREATED)
async def create_plan_day(plan_id: str, payload: TrainingPlanDayCreate, session: Session = Depends(db_session),) -> TrainingPlanDayRead:

    #cria novo dia no plano de treino
    try:
        plan = session.get(TrainingPlan, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plano de treino nao encontrado.")

        new_day = TrainingPlanDay(
            plan_id=plan_id,
            name=payload.name.strip(),
            order_index=payload.order_index,
            notes=payload.notes,
        )

        session.add(new_day)
        commit_or_rollback(session)
        session.refresh(new_day)
        return day_to_read(new_day)

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao criar novo dia no plano de treino.") from e 

#atualizar dia do plano de treino
@router.put("/days/{day_id}", response_model=TrainingPlanDayRead)
async def update_plan_day(day_id: str, payload: TrainingPlanDayUpdate, session: Session = Depends(db_session)) -> TrainingPlanDayRead:

    #atualiza dia do plano de treino existente
    try:
        day = session.get(TrainingPlanDay, day_id)
        if not day:
            raise HTTPException(status_code=404, detail="Dia do plano de treino nao encontrado.")

        #atualiza campos se fornecidos
        if payload.name is not None:
            day.name = payload.name.strip()
        if payload.order_index is not None:
            day.order_index = payload.order_index
        if payload.notes is not None:
            day.notes = payload.notes

        day.updated_at = utc_now()

        session.add(day)
        commit_or_rollback(session)
        session.refresh(day)
        return day_to_read(day)

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao atualizar o dia do plano de treino.") from e 

#delete o dia de treino
@router.delete("/days/{day_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan_day(day_id: str, session: Session = Depends(db_session)) -> None:
    #deleta dia do plano de treino existente
    try:
        day = session.get(TrainingPlanDay, day_id)
        if not day:
            raise HTTPException(status_code=404, detail="Dia do plano de treino nao encontrado.")

        #Delete manual das dependencias
        day_exercises = session.exec(select(PlanDayExercise).where(PlanDayExercise.plan_day_id == day.id)).all()
        for de in day_exercises:
            loads = session.exec(select(PlanExerciseSetLoad).where(PlanExerciseSetLoad.plan_day_exercise_id == de.id)).all()
            for l in loads:
                session.delete(l)
            session.delete(de)

        session.delete(day)
        commit_or_rollback(session)
        return None

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao deletar o dia do plano de treino.") from e  
    
#===================
#CRUD: Exercicios do dia
#===================
def _day_exercise_with_details_to_read(
    pde: PlanDayExercise, 
    exercise: Exercise
) -> PlanDayExerciseRead:
    """
    Converte PlanDayExercise + Exercise em schema de resposta.
    
    Args:
        pde: Exercício do dia do plano
        exercise: Detalhes do exercício do catálogo
    
    Returns:
        Schema de resposta com todos os campos populados
    """
    return PlanDayExerciseRead(
        # Campos do PlanDayExercise
        id=pde.id,
        plan_day_id=pde.plan_day_id,
        exercise_id=pde.exercise_id,
        exercise_name=exercise.name,
        exercise_muscles=exercise.muscles,
        exercise_url=exercise.url,
        order_index=pde.order_index,
        sets=pde.sets,
        reps_range=pde.reps_range,
        rest_range_seconds=pde.rest_range_seconds,
        tempo=pde.tempo,
        is_superset_group=pde.is_superset_group,
        substitution_allowed=pde.substitution_allowed,
        notes=pde.notes,
        created_at=pde.created_at,
        updated_at=pde.updated_at
    )

#get dos exercicios do dia do plano de treino
@router.get("/days/{day_id}/exercises", response_model=List[PlanDayExerciseRead])
async def list_day_exercises(day_id: str, session: Session = Depends(db_session),) -> List[PlanDayExerciseRead]:

    #lista os exercicios de um dia do plano de treino
    try:
        day = session.get(TrainingPlanDay, day_id)
        if not day:
            raise HTTPException(status_code=404, detail="Dia do plano de treino nao encontrado.")

        stmt = (
            select(PlanDayExercise, Exercise)
            .join(Exercise, PlanDayExercise.exercise_id == Exercise.id)
            .where(PlanDayExercise.plan_day_id == day_id)
            .order_by(PlanDayExercise.order_index.asc())
        )
        
        results = session.exec(stmt).all()
        
        # Converter para schema de resposta
        return [
            _day_exercise_with_details_to_read(pde, exercise)
            for pde, exercise in results
        ]

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao listar os exercicios do dia do plano de treino.") from e

#criar novo exercicio no dia do plano de treino
@router.post("/days/{day_id}/exercises", response_model=PlanDayExerciseRead, status_code=status.HTTP_201_CREATED)
async def create_day_exercise(day_id: str,payload: PlanDayExerciseCreate, session: Session = Depends(db_session),) -> PlanDayExerciseRead:
    
    #cria novo exercicio no dia do plano de treino
    try:
        day = session.get(TrainingPlanDay, payload.plan_day_id)
        if not day:
            raise HTTPException(status_code=404, detail="Dia do plano de treino nao encontrado.")

        exercise = session.get(Exercise, payload.exercise_id)
        if not exercise:
            raise HTTPException(status_code=404, detail="Exercicio nao encontrado.")

        new_day_exercise = PlanDayExercise(
            plan_day_id=payload.plan_day_id,
            exercise_id=payload.exercise_id,
            order_index=payload.order_index,
            sets=payload.sets,
            reps_range=payload.reps_range.strip(),
            rest_range_seconds=payload.rest_range_seconds.strip() if payload.rest_range_seconds else None,
            tempo=payload.tempo.strip() if payload.tempo else None,
            is_superset_group=payload.is_superset_group.strip() if payload.is_superset_group else None,
            substitution_allowed=payload.substitution_allowed,
            notes=payload.notes,
        )

        session.add(new_day_exercise)
        commit_or_rollback(session)
        session.refresh(new_day_exercise)
        return _day_exercise_to_read(new_day_exercise, session)
    except HTTPException:
        raise

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao criar novo exercicio no dia do plano de treino.") from e
    
#atualizar exercicio do dia do plano de treino
@router.put("/days/exercises/{day_exercise_id}", response_model=PlanDayExerciseRead)
async def update_day_exercise(day_exercise_id: str, payload: PlanDayExerciseUpdate, session: Session = Depends(db_session)) -> PlanDayExerciseRead:

    #atualiza exercicio do dia do plano de treino existente
    try:
        day_exercise = session.get(PlanDayExercise, day_exercise_id)
        if not day_exercise:
            raise HTTPException(status_code=404, detail="Exercicio do dia do plano de treino nao encontrado.")

        if payload.exercise_id is not None:
            exercise = session.get(Exercise, payload.exercise_id)
            if not exercise:
                raise HTTPException(status_code=404, detail="Exercicio nao encontrado.")
            day_exercise.exercise_id = payload.exercise_id
        
        if payload.order_index is not None:
            day_exercise.order_index = payload.order_index
        if payload.sets is not None:
            day_exercise.sets = payload.sets
        if payload.reps_range is not None:
            day_exercise.reps_range = payload.reps_range.strip()
        if payload.rest_range_seconds is not None:
            day_exercise.rest_range_seconds = payload.rest_range_seconds.strip() if payload.rest_range_seconds else None
        if payload.tempo is not None:
            day_exercise.tempo = payload.tempo.strip() if payload.tempo else None
        if payload.is_superset_group is not None:
            day_exercise.is_superset_group = payload.is_superset_group.strip() if payload.is_superset_group else None
        if payload.substitution_allowed is not None:
            day_exercise.substitution_allowed = payload.substitution_allowed
        if payload.notes is not None:
            day_exercise.notes = payload.notes
        
        day_exercise.updated_at = utc_now()
        session.add(day_exercise)
        commit_or_rollback(session)
        session.refresh(day_exercise)
        return _day_exercise_to_read(day_exercise, session)

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao atualizar o exercicio do dia do plano de treino.") from e

#delete o exercicio do dia do plano de treino
@router.delete("/days/exercises/{day_exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_day_exercise(day_exercise_id: str, session: Session = Depends(db_session)) -> None:

    #delete do exercicio do plano de treino
    try:
        day_exercise = session.get(PlanDayExercise, day_exercise_id)
        if not day_exercise:
            raise HTTPException(status_code=404, detail="Exercicio do dia do plano de treino nao encontrado.")

        #delete manual das cargas associadas
        loads = session.exec(select(PlanExerciseSetLoad).where(PlanExerciseSetLoad.plan_day_exercise_id == day_exercise.id)).all()
        for l in loads:
            session.delete(l)

        session.delete(day_exercise)
        commit_or_rollback(session)
        return None
    
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao deletar o exercicio do dia do plano de treino.") from e

#===================
#CRUD: Cargas por série
#===================


#get das cargas por série do exercicio do dia do plano de treino
@router.get("/days/exercises/{day_exercise_id}/loads", response_model=List[PlanExerciseSetLoadRead])
async def list_set_loads(day_exercise_id: str, session: Session = Depends(db_session),) -> List[PlanExerciseSetLoadRead]:

    #lista as cargas por série de um exercicio do dia do plano de treino
    try:
        day_exercise = session.get(PlanDayExercise, day_exercise_id)
        if not day_exercise:
            raise HTTPException(status_code=404, detail="Exercicio do dia do plano de treino nao encontrado.")

         #Query com JOIN para buscar tudo de uma vez
        stmt = (
            select(PlanExerciseSetLoad, PlanDayExercise, Exercise)
            .join(PlanDayExercise, PlanExerciseSetLoad.plan_day_exercise_id == PlanDayExercise.id)
            .join(Exercise, PlanDayExercise.exercise_id == Exercise.id)
            .where(PlanExerciseSetLoad.plan_day_exercise_id == day_exercise_id)
            .order_by(PlanExerciseSetLoad.set_number.asc())
        )
        
        results = session.exec(stmt).all()
        
        # Converter para schema usando função auxiliar
        return [
            _set_load_with_details_to_read(load, day_ex, ex)
            for load, day_ex, ex in results
        ]
    
    except HTTPException:
        raise

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao listar as cargas por série do exercicio do dia do plano de treino.") from e

#criar nova carga por série do exercicio do dia do plano de treino
@router.post("/days/exercises/{day_exercise_id}/loads", response_model=PlanExerciseSetLoadRead, status_code=status.HTTP_201_CREATED)
async def create_set_load(day_exercise_id: str,payload: PlanExerciseSetLoadCreate, session: Session = Depends(db_session),) -> PlanExerciseSetLoadRead:
    
    #cria nova carga por série do exercicio do dia do plano de treino
    try:
        day_exercise = session.get(PlanDayExercise, day_exercise_id)
        if not day_exercise:
            raise HTTPException(status_code=404, detail="Exercicio do dia do plano de treino nao encontrado.")

        if payload.set_number > day_exercise.sets:
            raise HTTPException(status_code=400, detail="O número da série não pode ser maior que o número total de séries definido para este exercício do dia do plano de treino.")
        # Verificar se já existe carga para esta série
        existing_load = session.exec(
            select(PlanExerciseSetLoad)
            .where(
                PlanExerciseSetLoad.plan_day_exercise_id == day_exercise_id,
                PlanExerciseSetLoad.set_number == payload.set_number
            )
        ).first()

        if existing_load:
            raise HTTPException(status_code=400, detail=f"Já existe uma carga definida para a série {payload.set_number} deste exercício do dia do plano de treino.")
        
        new_load = PlanExerciseSetLoad(
            plan_day_exercise_id=day_exercise_id, 
            set_number=payload.set_number,
            load_kg=payload.load_kg,
            notes=payload.notes.strip() if payload.notes else None,
        )

        session.add(new_load)
        commit_or_rollback(session)
        session.refresh(new_load)

        return _set_load_to_read(new_load, session)
    
    except HTTPException:
        raise
    
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao criar nova carga por série do exercicio do dia do plano de treino.") from e
    
#atualizar carga por série do exercicio do dia do plano de treino
@router.put("/days/exercises/loads/{set_load_id}", response_model=PlanExerciseSetLoadRead)
async def update_set_load(set_load_id: str, payload: PlanExerciseSetLoadUpdate, session: Session = Depends(db_session)) -> PlanExerciseSetLoadRead:

    #atualiza carga por série do exercicio do dia do plano de treino existente
    try:
        set_load = session.get(PlanExerciseSetLoad, set_load_id)
        if not set_load:
            raise HTTPException(status_code=404, detail="Carga por série do exercicio do dia do plano de treino nao encontrada.")

        if payload.set_number is not None:
            day_exercise = session.get(PlanDayExercise, set_load.plan_day_exercise_id)
            if payload.set_number > day_exercise.sets:
                raise HTTPException(status_code=400, detail="O número da série não pode ser maior que o número total de séries definido para este exercício do dia do plano de treino.")
            
            set_load.set_number = payload.set_number
        
        if payload.load_kg is not None:
            set_load.load_kg = payload.load_kg
        
        if payload.notes is not None:
            set_load.notes = payload.notes
        
        set_load.updated_at = utc_now()
        
        session.add(set_load)
        commit_or_rollback(session)
        session.refresh(set_load)
        return _set_load_to_read(set_load, session)
    
    except HTTPException:
        raise

    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Conflito: set_number duplicado para este exercício.") from e
    
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao atualizar a carga por série do exercicio do dia do plano de treino.") from e
    
#delete da carga por série do exercicio do dia do plano de treino
@router.delete("/set-loads/{set_load_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_set_load(set_load_id: str, session: Session = Depends(db_session)) -> None:

    #delete da carga por série do exercicio do dia do plano de treino
    try:
        set_load = session.get(PlanExerciseSetLoad, set_load_id)
        if not set_load:
            raise HTTPException(status_code=404, detail="Carga por série do exercicio do dia do plano de treino nao encontrada.")

        session.delete(set_load)
        commit_or_rollback(session)
        return None
    
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao deletar a carga por série do exercicio do dia do plano de treino.") from e

#===================
#Plano ativo do cliente
#===================

"""Obtém o plano ativo do cliente (se existir)."""
@router.get("/active-plan/{client_id}", response_model=Optional[ClientActivePlanRead])
async def get_active_plan(client_id: str, session: Session = Depends(db_session),) -> Optional[ClientActivePlanRead]:
    
    #obtem o plano ativo do cliente (se existir)
    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        if client.archived_at is not None:
            raise HTTPException(status_code=400, detail="Cliente está arquivado.")

        active_plan = session.exec(
            select(ClientActivePlan)
            .where(ClientActivePlan.client_id == client_id)
            .where(ClientActivePlan.active_to == None)
        ).first()

        if not active_plan:
            return None

        return _active_to_read(active_plan, session)
    
    except HTTPException:
        raise

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao obter o plano ativo do cliente.") from e

@router.post("/active-plan", response_model=ClientActivePlanRead, status_code=status.HTTP_201_CREATED)
async def set_active_plan(payload: ClientActivePlanCreate, session: Session = Depends(db_session)) -> ClientActivePlanRead:

    try:
        client = session.get(Client, payload.client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        if client.archived_at is not None:
            raise HTTPException(status_code=400, detail="Cliente está arquivado.")

        plan = session.get(TrainingPlan, payload.training_plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plano de treino não encontrado.")

        if plan.client_id is not None and plan.client_id != payload.client_id:
            raise HTTPException(status_code=400, detail="Plano de treino não está associado ao cliente.")

        today = payload.active_from or utc_now()

        # Fecha qualquer plano ativo anterior
        active_plan = session.exec(
            select(ClientActivePlan)
            .where(ClientActivePlan.client_id == payload.client_id)
            .where(ClientActivePlan.active_to == None)
        ).first()

        if active_plan:
            #idempotência: se já é o mesmo plano, não faz nada
            if active_plan.training_plan_id == payload.training_plan_id:
                return _active_to_read(active_plan, session)

            active_plan.active_to = today
            active_plan.updated_at = utc_now()
            session.add(active_plan)
            commit_or_rollback(session)

        # Define o novo plano ativo
        new_active_plan = ClientActivePlan(
            client_id=payload.client_id,
            training_plan_id=payload.training_plan_id,
            active_from=today,
            active_to=None
        )

        session.add(new_active_plan)
        commit_or_rollback(session)
        session.refresh(new_active_plan)
        return _active_to_read(new_active_plan, session)
    
    except HTTPException:
        raise

    except IntegrityError as e:
        # Quando o índice parcial UNIQUE existir, isto cobre corrida/conflito.
        raise HTTPException(status_code=409, detail="Já existe um plano ativo para este cliente.") from e

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao definir o plano ativo do cliente.") from e

#Encerra o plano ativo do cliente (active_to = hoje).
@router.post("/clients/{client_id}/active/close", response_model=Optional[ClientActivePlanRead])
async def close_active_plan(client_id: str, session: Session = Depends(db_session)) -> Optional[ClientActivePlanRead]:

    try:
        client = session.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        if client.archived_at is not None:
            raise HTTPException(status_code=400, detail="Cliente está arquivado.")

        active_plan = session.exec(
            select(ClientActivePlan)
            .where(ClientActivePlan.client_id == client_id)
            .where(ClientActivePlan.active_to.is_(None))
            .limit(1)
        ).first()

        if not active_plan:
            return None

        active_plan.active_to = utc_now()
        active_plan.updated_at = utc_now()
        session.add(active_plan)
        commit_or_rollback(session)
        session.refresh(active_plan)
        return _active_to_read(active_plan, session)
    
    except HTTPException:
        raise

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao encerrar o plano ativo do cliente.") from e
    
    #===================
    #Clona plano de treino para cliente
    #===================

@router.post("/{template_plan_id}/clone-to-client/{client_id}", response_model=TrainingPlanRead, status_code=status.HTTP_201_CREATED)
async def clone_template_to_client(template_plan_id: str, payload: ClonePlanToClientCreate, session: Session = Depends(db_session)) -> TrainingPlanRead:
    
    # =========================
    # 1) Validar cliente
    # =========================
    client = session.get(Client, payload.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    if client.archived_at is not None:
        raise HTTPException(status_code=400, detail="Cliente está arquivado.")

    # =========================
    # 2) Validar template
    # =========================
    template = session.get(TrainingPlan, template_plan_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado.")
    if template.client_id is not None:
        raise HTTPException(status_code=400, detail="O plano indicado não é template (tem client_id).")

    # =========================
    # 3) Criar novo plano do cliente
    # =========================
    new_plan = TrainingPlan(
        client_id=payload.client_id,
        name=(payload.name.strip() if payload.name else f"{template.name} - {client.name}"),
        status=("published" if payload.activate else "draft"),
        start_date=template.start_date,
        end_date=template.end_date,
        notes=template.notes,
    )
    session.add(new_plan)

    try:
        # flush: garante new_plan.id antes do commit
        session.flush()

        # =========================
        # 4) Copiar dias
        # =========================
        template_days = session.exec(
            select(TrainingPlanDay)
            .where(TrainingPlanDay.plan_id == template_plan_id)
            .order_by(TrainingPlanDay.order_index.asc(), TrainingPlanDay.created_at.asc())
        ).all()

        # Mapa: old_day_id -> new_day_id
        day_map: dict[str, str] = {}

        for d in template_days:
            nd = TrainingPlanDay(
                plan_id=new_plan.id,
                name=d.name,
                order_index=d.order_index,
                notes=d.notes,
            )
            session.add(nd)
            session.flush()
            day_map[d.id] = nd.id

        # =========================
        # 5) Copiar exercícios dos dias
        # =========================
        # Mapa: old_day_ex_id -> new_day_ex_id
        day_ex_map: dict[str, str] = {}

        for old_day_id, new_day_id in day_map.items():
            old_exercises = session.exec(
                select(PlanDayExercise)
                .where(PlanDayExercise.plan_day_id == old_day_id)
                .order_by(PlanDayExercise.order_index.asc(), PlanDayExercise.created_at.asc())
            ).all()

            for x in old_exercises:
                nx = PlanDayExercise(
                    plan_day_id=new_day_id,
                    exercise_id=x.exercise_id,
                    order_index=x.order_index,
                    sets=x.sets,
                    reps_range=x.reps_range,
                    rest_range_seconds=x.rest_range_seconds,
                    tempo=x.tempo,
                    is_superset_group=x.is_superset_group,
                    substitution_allowed=x.substitution_allowed,
                    notes=x.notes,
                )
                session.add(nx)
                session.flush()
                day_ex_map[x.id] = nx.id

        # =========================
        # 6) Copiar loads por série
        # =========================
        for old_day_ex_id, new_day_ex_id in day_ex_map.items():
            old_loads = session.exec(
                select(PlanExerciseSetLoad)
                .where(PlanExerciseSetLoad.plan_day_exercise_id == old_day_ex_id)
                .order_by(PlanExerciseSetLoad.set_number.asc())
            ).all()

            for l in old_loads:
                nl = PlanExerciseSetLoad(
                    plan_day_exercise_id=new_day_ex_id,
                    set_number=l.set_number,
                    load_kg=l.load_kg,
                    notes=l.notes,
                )
                session.add(nl)

        # =========================
        # 7) Opcional: ativar plano
        # =========================
        if payload.activate:
            today = payload.activate_from or utc_now()

            current = session.exec(
                select(ClientActivePlan)
                .where(ClientActivePlan.client_id == payload.client_id)
                .where(ClientActivePlan.active_to.is_(None))
                .limit(1)
            ).first()

            if current:
                # fecha o anterior
                current.active_to = today
                current.updated_at = utc_now()
                session.add(current)

            new_active = ClientActivePlan(
                client_id=payload.client_id,
                training_plan_id=new_plan.id,
                active_from=today,
                active_to=None,
            )
            session.add(new_active)

        # commit final (tudo ou nada)
        session.commit()
        session.refresh(new_plan)
        return _plan_to_read(new_plan)

    except HTTPException:
        raise
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(status_code=409, detail="Conflito de integridade ao clonar o plano.") from e
    except SQLAlchemyError as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro ao clonar o plano.") from e