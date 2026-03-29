"""
Router para o sistema de alimentação.

Endpoints Foods (Alimento):
- POST /nutrition/foods/ : Criar um novo alimento
- GET /nutrition/foods/ : Listar todos os alimentos
- GET /nutrition/foods/{food_id} : Obter detalhes de um alimento específico
- PATCH /nutrition/foods/{food_id} : Atualizar um alimento específico
- DeLETE /nutrition/foods/{food_id} : desactivar (soft)

Endpoints Cálculo de macros:
- GET /nutrition/activity-factors : Listar fatores de atividade física disponíveis para cálculo de TMB
- GET /nutrition/plan-types : Listar tipos de plano alimentar disponíveis para cálculo de TMB
- POST /nutrition/calculate-macros : Calcular os macros recomendados para um cliente

Endpoints relacionados a plano alimentar:
- POST /nutrition/meal-plans/ : Criar um novo plano alimentar
- GET /nutrition/meal-plans/client/{client_id} : Listar o plano alimentar do cliente
- GET /nutrition/meal-plans/{meal_plan_id} : Obter detalhes de um plano alimentar específico
- PATCH /nutrition/meal-plans/{meal_plan_id} : Atualizar um plano alimentar específico
- DELETE /nutrition/meal-plans/{meal_plan_id} : Arquivar um plano alimentar
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session
from sqlalchemy.exc import SQLAlchemyError
from typing import List, Optional

from app.api.deps import db_session
from app.core.security import get_current_user, require_trainer
from app.core.db_errors import commit_or_rollback
from app.db.models.client import Client
from app.db.models.nutrition import PLAN_TYPE_OPTIONS, Food
import app.crud.nutrition as crud
from app.services.macro_calculator import (
    calculate_tmb_all_formulas, 
    calculate_macros_from_percentages, 
    calculate_macros_from_grams_per_kg, 
    get_activity_factor_options, 
    ACTIVITY_FACTORS,
)
from app.schemas.nutrition import (
    FoodCreate,
    FoodRead,
    FoodUpdate,
    MealPlanCreate,
    MealPlanRead,
    MealPlanUpdate,
    MacroCalculationRequest,
    MacroCalculationResponse,
    FormulaResult,
    MacroDistribution,
)

router = APIRouter(prefix="/nutrition", tags=["Nutrition"])

# =============================================================================
# Helpers internos
# =============================================================================

def _assert_food_owner(food: Food, trainer_id: str) -> None:
    """
    Verifica se o alimento pertence ao trainer autenticado.
    Levanta 403 se não pertencer.
 
    Nota: alimentos globais (owner_trainer_id = None) nunca passam nesta
    verificação — são bloqueados antes desta função ser chamada.
    """

    if food.owner_trainer_id is None:
        raise HTTPException(status_code=403, detail="Alimento global não pode ser modificado aqui.")

    if food.owner_trainer_id != trainer_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este alimento.")

#---------------------------------------------
#Endpoints de referência (sem autenticação)
#---------------------------------------------

@router.get("/activity-factors")
def list_activity_factors() -> list:
    #Lista os fatores de atividade física disponíveis para cálculo de TMB.
    return get_activity_factor_options()

@router.get("/plan-types")
def list_plan_types() -> list:
    #Lista os tipos de plano alimentar disponíveis para cálculo de TMB.
    return [{"key": key, "label": label} for key, label in PLAN_TYPE_OPTIONS.items()]

#---------------------------------------------
#Cálculo de macros
#---------------------------------------------

@router.post("/calculate-macros", response_model=MacroCalculationResponse)
def calculate_macros(payload: MacroCalculationRequest) -> MacroCalculationResponse:
    #Calcula os macros recomendados para um cliente com base nos dados fornecidos e na distribuição de macronutrientes desejada.
    try:
        #Calcula TMB/TDEE pelas 3 fórmulas
        tmb_results = calculate_tmb_all_formulas(
            weight_kg=payload.weight_kg,
            height_cm=payload.height_cm,
            age=payload.age,
            sex=payload.sex,
            activity_key=payload.activity_key,
        )

        formula_reponses =[
            FormulaResult(
                formula=r.formula,
                label=r.label,
                tmb=r.tmb,
                tdee=r.tdee,
            )
            for r in tmb_results
        ]

        #Calcula os macros com base na distribuição desejada
        macros_distribution = None
        if payload.kcal_target is not None and payload.method is not None:
            try:
                if payload.method == "percentages":
                    macros = calculate_macros_from_percentages(
                        kcal_target=payload.kcal_target,
                        carbs_pct=payload.carbs_pct,
                        protein_pct=payload.protein_pct,
                        fats_pct=payload.fats_pct,
                        weight_kg=payload.weight_kg,
                    )
                else: #grams_per_kg
                    # gramas derivadas de g/kg * peso
                    macros = calculate_macros_from_grams_per_kg(
                        protein_g_per_kg=payload.protein_g_per_kg,
                        carbs_g_per_kg=payload.carbs_g_per_kg,
                        fats_g_per_kg=payload.fats_g_per_kg,
                        weight_kg=payload.weight_kg,
                    )

                macros_distribution = MacroDistribution(
                    method=payload.method,
                    kcal_target=payload.kcal_target,
                    protein_g=macros.protein_g,
                    carbs_g=macros.carbs_g,
                    fats_g=macros.fats_g,
                    kcal_from_macros=macros.kcal_from_macros,
                    protein_g_per_kg=macros.protein_g_per_kg,
                    carbs_g_per_kg=macros.carbs_g_per_kg,
                    fats_g_per_kg=macros.fats_g_per_kg,
                    protein_pct=macros.protein_pct,
                    carbs_pct=macros.carbs_pct,
                    fats_pct=macros.fats_pct,
                )
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
            
        #Obtém label e factor de atividade física
        activity_options = {o["key"]: o for o in get_activity_factor_options()}
        activity_info = activity_options.get(payload.activity_key, {})

        return MacroCalculationResponse(
            weight_kg=payload.weight_kg,
            height_cm=payload.height_cm,
            age=payload.age,
            sex=payload.sex,
            activity_key=payload.activity_key,
            activity_label=activity_info.get("label", payload.activity_key),
            activity_factor=ACTIVITY_FACTORS[payload.activity_key],
            formulas=formula_reponses,
            macros_distribution=macros_distribution,
        )
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Erro inesperado no cálculo.") from e

# =============================================================================
# Foods — catálogo de alimentos
# =============================================================================

# ======================
#Create de alimentos
# ======================

@router.post("/foods/", response_model=FoodRead, status_code=status.HTTP_201_CREATED)
def create_food(
    payload: FoodCreate, 
    session: Session = Depends(db_session),
    current_user=Depends(require_trainer),
    ) -> FoodRead:
    #Cria um alimento privado para o trainer autenticado.
    #owner_trainer_id é preenchido automaticamente com o ID do trainer.
    
    try:
        food = crud.create_food(session, payload, owner_trainer_id=current_user.id)
        commit_or_rollback(session)
        #refresh carrega kcal gerado no BD
        session.refresh(food)
        return FoodRead.model_validate(food)
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao criar alimento.") from e


@router.get("/foods/", response_model=List[FoodRead])
def list_foods(
    active_only: bool = Query(True, description="Apenas alimentos ativos"), 
    session: Session = Depends(db_session),
    current_user=Depends(require_trainer),
    ) -> List[FoodRead]:
    
    #Lista alimentos visíveis para o trainer:
    #  - Alimentos globais (owner_trainer_id IS NULL) — visíveis a todos
    #  - Alimentos privados do trainer autenticado
    #O filtro de tenant é aplicado no CRUD para garantir isolamento.

    try:
        foods = crud.list_foods(session, trainer_id=current_user.id, active_only=active_only)
        return [FoodRead.model_validate(food) for food in foods]
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao listar alimentos.") from e
    

@router.get("/foods/{food_id}", response_model=FoodRead)
def get_food(
    food_id: str,
    session: Session = Depends(db_session),
    current_user=Depends(require_trainer),
    ) -> FoodRead:

    #Obtém detalhes de um alimento específico por UUID.
    
    try:
        food = crud.get_food_by_id(session, food_id)
        if not food:
            raise HTTPException(status_code=404, detail="Alimento não encontrado.")
        return FoodRead.model_validate(food)
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao obter alimento.") from e
    
#---------------------------------------------
#Update de alimento específico
#---------------------------------------------
@router.patch("/foods/{food_id}", response_model=FoodRead)
def update_food(
    food_id: str, 
    payload: FoodUpdate, 
    session: Session = Depends(db_session),
    current_user=Depends(require_trainer),
    ) -> FoodRead:

    #Actualiza um alimento privado do trainer.
    #Alimentos globais (owner_trainer_id = None) não podem ser editados aqui.

    try:
        food = crud.get_food_by_id(session, food_id)
        if not food:
            raise HTTPException(status_code=404, detail="Alimento não encontrado.")
        
        _assert_food_owner(food, current_user.id)

        food = crud.update_food(session, food, payload)
        commit_or_rollback(session)
        session.refresh(food) #refresh carrega kcal gerado no BD
        return FoodRead.model_validate(food)
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao atualizar alimento.") from e
    
#---------------------------------------------
#Delete (soft) de alimento específico
#---------------------------------------------
@router.delete("/foods/{food_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_food(
    food_id: str, 
    session: Session = Depends(db_session), 
    current_user=Depends(require_trainer),
) -> None:
    
    #Desativa um alimento privado (soft delete — is_active=False).
    #Alimentos globais não podem ser desativados aqui.

    try:
        #Verifica se o alimento existe
        food = crud.get_food_by_id(session, food_id)
        if not food:
            raise HTTPException(status_code=404, detail="Alimento não encontrado.")
        
        # Verifica se o alimento pertence ao trainer autenticado
        _assert_food_owner(food, current_user.id)

        #Verifica se o alimento já está inativo
        if not food.is_active:
            raise HTTPException(status_code=400, detail="Alimento já está inativo.")
        
        #Desativa o alimento
        food.is_active = False
        session.add(food)
        commit_or_rollback(session)
        return None
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao deletar alimento.") from e
    
# =============================================================================
# Meal Plans — planos alimentares
# =============================================================================

@router.post("/meal-plans/", response_model=MealPlanRead, status_code=status.HTTP_201_CREATED)
def create_meal_plan(
    payload: MealPlanCreate, 
    session: Session = Depends(db_session),
    current_user=Depends(require_trainer),
) -> MealPlanRead:
    #Cria um plano alimentar para um cliente do trainer autenticado.


    try:
        #Verifica se o cliente existe
        client = session.get(Client, payload.client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        #Verifca se o cliente está ativo
        if client.archived_at:
            raise HTTPException(status_code=400, detail="Não é possível criar plano alimentar para cliente arquivado.")
        
        #valida que todos os foods_id fornecidos nas refeições existem e estão ativos
        for meal in payload.meals:
            for item in meal.items:
                food = crud.get_food_by_id(session, item.food_id)
                if not food or not food.is_active:
                    raise HTTPException(status_code=400, detail=f"Alimento com id {item.food_id} não encontrado ou inativo.")
                
        
        meal_plan = crud.create_meal_plan(session, payload)
        commit_or_rollback(session)
        session.refresh(meal_plan) #refresh carrega os dados gerados no BD, incluindo os macros agregados calculados no crud
        return crud.build_meal_plan_read(session, meal_plan)
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao criar plano alimentar.") from e
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao criar plano alimentar.") from e


@router.get("/meal-plans/client/{client_id}", response_model=List[MealPlanRead])
def list_meal_plans_by_client(
    client_id: str, 
    plan_type: Optional[str] = Query(default=None), 
    include_archived: bool = False, 
    session: Session = Depends(db_session),
    current_user=Depends(require_trainer),
) -> List[MealPlanRead]:
    # Lista os planos alimentares de um cliente do trainer autenticado.

    try:

        #Verifica se o cliente existe
        if not session.get(Client, client_id):
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")
        
        if plan_type and plan_type not in PLAN_TYPE_OPTIONS:
            valid = ", ".join(PLAN_TYPE_OPTIONS.keys())
            raise HTTPException(status_code=422, detail=f"Tipo de plano inválido. Valores válidos: {valid}")
        
        meal_plans = crud.list_meal_plans_by_client(session, client_id, include_archived=include_archived)
        return [crud.build_meal_plan_read(session, mp) for mp in meal_plans]
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao listar planos alimentares.") from e
    


@router.get("/meal-plans/{meal_plan_id}", response_model=MealPlanRead)
def get_meal_plan(
    meal_plan_id: str, 
    session: Session = Depends(db_session),
    current_user=Depends(require_trainer),
) -> MealPlanRead:
    
    #Obtém detalhes de um plano alimentar específico por ID, incluindo suas refeições, itens e macros agregados.

    try:
        meal_plan = crud.get_meal_plan_by_id(session, meal_plan_id)
        if not meal_plan:
            raise HTTPException(status_code=404, detail="Plano alimentar não encontrado.")
        
        return crud.build_meal_plan_read(session, meal_plan)
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao obter plano alimentar.") from e
    

@router.patch("/meal-plans/{meal_plan_id}", response_model=MealPlanRead)
def update_meal_plan(
    meal_plan_id: str, 
    payload: MealPlanUpdate, 
    session: Session = Depends(db_session),
    current_user=Depends(require_trainer),
) -> MealPlanRead:
    # Atualiza os detalhes de um plano alimentar específico por ID. Apenas os campos fornecidos no payload serão atualizados.

    try:
        meal_plan = crud.get_meal_plan_by_id(session, meal_plan_id)
        if not meal_plan:
            raise HTTPException(status_code=404, detail="Plano alimentar não encontrado.")
        if meal_plan.archived_at:
            raise HTTPException(status_code=400, detail="Não é possível atualizar um plano alimentar arquivado.")
        
        meal_plan = crud.update_meal_plan(session, meal_plan, payload)
        commit_or_rollback(session)
        session.refresh(meal_plan) #refresh carrega os dados gerados no BD, incluindo os macros agregados calculados no crud
        return crud.build_meal_plan_read(session, meal_plan)
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao atualizar plano alimentar.") from e
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail="Erro inesperado ao atualizar plano alimentar.") from e
    

@router.delete("/meal-plans/{meal_plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal_plan(
    meal_plan_id: str, 
    session: Session = Depends(db_session),
    current_user=Depends(require_trainer),
) -> None:
    
    #Realiza um soft delete (arquivamento) de um plano alimentar específico por ID. O plano alimentar não é removido da base de dados, mas é marcado como arquivado (archived_at=timestamp) e não aparecerá mais nas listagens ativas.
    
    try:
        meal_plan = crud.get_meal_plan_by_id(session, meal_plan_id)
        if not meal_plan:
            raise HTTPException(status_code=404, detail="Plano alimentar não encontrado.")
        
        if meal_plan.archived_at:
            return None #se já está arquivado, não faz nada
        
        crud.soft_delete_meal_plan(session, meal_plan)
        commit_or_rollback(session)
        return None
    
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Erro ao deletar plano alimentar.") from e