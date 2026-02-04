from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from typing import List, Optional

from app.api.deps import db_session
from app.core.db_errors import commit_or_rollback
from app.db.models.client import Client
from app.db.models.training import (TrainingPlan, TrainingPlanDay, PlanDayExercise, PlanExerciseSetLoad, ClientActivePlan, Exercise,)
from app.schemas.training import (TrainingPlanCreate, TrainingPlanRead, TrainingPlanUpdate, TrainingPlanDayCreate, TrainingPlanDayRead, TrainingPlanDayUpdate,
    PlanDayExerciseCreate, PlanDayExerciseRead, PlanDayExerciseUpdate, PlanExerciseSetLoadCreate, PlanExerciseSetLoadRead, PlanExerciseSetLoadUpdate, ClientActivePlanSet,
    ClientActivePlanRead,)
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

def _day_exercise_to_read(de: PlanDayExercise) -> PlanDayExerciseRead:
    return PlanDayExerciseRead(
        id=de.id,
        plan_day_id=de.plan_day_id,
        exercise_id=de.exercise_id,
        sets=de.sets,
        reps_range=de.reps_range,
        rest_range_seconds=de.rest_range_seconds,
        tempo=de.tempo,
        is_superset_group=de.is_superset_group,
        substitution_allowed=de.substitution_allowed,
        created_at=de.created_at,
        updated_at=de.updated_at
    )

def _set_load_to_read(sl: PlanExerciseSetLoad) -> PlanExerciseSetLoadRead:
    return PlanExerciseSetLoadRead(
        id=sl.id,
        plan_day_exercise_id=sl.plan_day_exercise_id,
        set_number=sl.set_number,
        load_kg=sl.load_kg,
        notes=sl.notes,
        created_at=sl.created_at,
        updated_at=sl.updated_at
    )

def _active_to_read(a: ClientActivePlan) -> ClientActivePlanRead:
    return ClientActivePlanRead(
        id=a.id,
        client_id=a.client_id,
        plan_id=a.plan_id,
        active_from=a.active_from,
        active_to=a.active_to,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )

#======================
#CRUD Training plans
#======================

#get todos os planos de treino
@router.get("/", response_model=List[TrainingPlanRead])
def list_plans(
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
@router.post("", response_model=TrainingPlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: TrainingPlanCreate,
    session: Session = Depends(db_session)
) -> TrainingPlanRead:
    #cria novo plano de treino
    try:
        if payload.client_id:
            client = session.exec(
                select(Client).where(Client.id == payload.client_id.strip())
            ).first()
            if not client:
                raise HTTPException(status_code=404, detail="Cliente não encontrado.")
            if client.archived_at is not None:
                raise HTTPException(status_code=400, detail="Não é possível atribuir um plano de treino a um cliente arquivado.")
        
        plan = TrainingPlan(
            client_id=payload.client_id,
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
def update_plan(
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
def delete_plan(
    plan_id: str,
    session: Session = Depends(db_session)
) -> None:
    try:
        plan = session.get(TrainingPlan, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plano de treino não encontrado.")
        
        #Delete em cascade nao existe automaticamente em sqlmodel/sqlite
        #Delete manual para nao deixar registos orfãos
        days = session.exec(select(PlanDayExercise).where(PlanDayExercise.plan_day_id == plan.id)).all()
        for day in days:
            day_ex = session.exec(select(PlanDayExercise).where(PlanDayExercise.plan_day_id == day.id)).all()
            for x in day_ex:
                loads = session.exec(select(PlanExerciseSetLoad).where(PlanExerciseSetLoad.plan_day_exercise_id == x.id)).all()
                for l in loads:
                    session.delete(l)
                session.delete(x)
            session.delete(day)
        
        #remove mapeamentos de plano de treino (histórico)
        actives = session.exec(select(ClientActivePlan).where(ClientActivePlan.plan_id == plan.id)).all()
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
def list_plan_days(plan_id: str, session: Session = Depends(db_session),) -> List[TrainingPlanDayRead]:

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
def create_plan_day(payload: TrainingPlanDayCreate, session: Session = Depends(db_session),) -> TrainingPlanDayRead:

    #cria novo dia no plano de treino
    try:
        plan = session.get(TrainingPlan, payload.plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plano de treino nao encontrado.")

        new_day = TrainingPlanDay(
            plan_id=payload.plan_id,
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
def update_plan_day(day_id: str, payload: TrainingPlanDayUpdate, session: Session = Depends(db_session)) -> TrainingPlanDayRead:

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
def delete_plan_day(day_id: str, session: Session = Depends(db_session)) -> None:
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

#get dos exercicios do dia do plano de treino
@router.get("/days/{day_id}/exercises", response_model=List[PlanDayExerciseRead])
def list_day_exercises(day_id: str, session: Session = Depends(db_session),) -> List[PlanDayExerciseRead]:

    #lista os exercicios de um dia do plano de treino
    try:
        day = session.get(TrainingPlanDay, day_id)
        if not day:
            raise HTTPException(status_code=404, detail="Dia do plano de treino nao encontrado.")

        exercises = session.exec(
            select(PlanDayExercise)
            .where(PlanDayExercise.plan_day_id == day_id)
            .order_by(PlanDayExercise.created_at.asc())
        ).all()

        return [_day_exercise_to_read(e) for e in exercises]

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao listar os exercicios do dia do plano de treino.") from e

#criar novo exercicio no dia do plano de treino
@router.post("/days/{day_id}/exercises", response_model=PlanDayExerciseRead, status_code=status.HTTP_201_CREATED)
def create_day_exercise(payload: PlanDayExerciseCreate, session: Session = Depends(db_session),) -> PlanDayExerciseRead:
    
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
        return _day_exercise_to_read(new_day_exercise)
    
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao criar novo exercicio no dia do plano de treino.") from e
    
#atualizar exercicio do dia do plano de treino
@router.put("/days/exercises/{day_exercise_id}", response_model=PlanDayExerciseRead)
def update_day_exercise(day_exercise_id: str, payload: PlanDayExerciseUpdate, session: Session = Depends(db_session)) -> PlanDayExerciseRead:

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
        return _day_exercise_to_read(day_exercise)

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao atualizar o exercicio do dia do plano de treino.") from e

#delete o exercicio do dia do plano de treino
@router.delete("/days/exercises/{day_exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_day_exercise(day_exercise_id: str, session: Session = Depends(db_session)) -> None:

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