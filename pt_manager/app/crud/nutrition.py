"""
CRUD para o sistema de nutrição.

Responsabilidades:
-Queries á BD para alimentos, planos alimentares, refeições e itens do plano
- create_meal_plan / update_meal_plan lidam com plan_type e macro_targets
- build_meal_plan_read calcula 'adherence' quando targets estão definidos
- A unicidade de plano ativo por (client + plan_type) é verificada aqui
-Nunca levanta HTTPException - isso é responsabilidade dos routers
"""

from datetime import datetime,timezone
from typing import List, Optional

from sqlmodel import Session, select
from app.db.models.nutrition import Food, MealPlan, MealPlanMeal, MealPlanItem, PLAN_TYPE_OPTIONS
from app.schemas.nutrition import (
    FoodRead,
    FoodCreate,
    FoodUpdate, 
    MealPlanItemCreate, 
    MealPlanItemRead, 
    MacroSummary, 
    MealPlanMealCreate,
    MealPlanMealRead,
    MealPlanUpdate,
    MealPlanCreate,
    MealPlanRead,
    MacroAdherence,
)

#===================================
#FOOD CRUD
#===================================

def get_food_by_id(session: Session, food_id: str) -> Optional[Food]:
    return session.get(Food, food_id)

def list_foods(session: Session, active_only:bool = True, limit: int = 100) -> List[Food]:
    stmt = select(Food)
    if active_only:
        stmt =stmt.where(Food.is_active == True)
    stmt = stmt.order_by(Food.created_at.desc())
    stmt = stmt.limit(limit)
    return session.exec(stmt).all()

def create_food(session: Session, payload: FoodCreate) -> Food:
    #Cria um alimento no catálogo
    #Não inclui kcal no insert
    

    food = Food(
        name=payload.name,
        carbs=payload.carbs,
        protein=payload.protein,
        fats=payload.fats,
    )
    session.add(food)
    return food

def update_food(session: Session, food: Food, payload: FoodUpdate) -> Food:
    #Atualiza um alimento.
    #Não inclui kcal no update - é recalculada automaticamente pelo PostgreSQL.

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(food, key, value)
    food.updated_at = datetime.now(timezone.utc)
    session.add(food)
    return food

#===================================
#Macros e cálculos relacionados
#===================================

def _calculate_item_macros(food: Food, quantity_grams: float) -> dict:
    #Calcula os macros de um item do plano baseado no alimento e quantidade.
    #Formula: macro_real = (macro_100g / 100) * quantity_grams
    #O cálculo é feito no crud para evitar sobrecarga de lógica no banco e permitir mais flexibilidade no futuro (ex: ajustes personalizados, promoções, etc)

    factor = quantity_grams / 100.0
    protein = round((food.protein or 0) * factor, 2)
    carbs=round((food.carbs or 0) * factor, 2)
    fats=round((food.fats or 0) * factor, 2),
    kcal=round(protein * 4 + carbs * 4 + fats * 9, 2)
    return {"protein_g": protein, "carbs_g": carbs, "fats_g": fats, "kcal": kcal}

def _sum_macros(macros_list: List[dict]) -> MacroSummary:
    """
    Soma uma lista de macros (cada item é um dict com protein_g, carbs_g, fats_g, kcal) e retorna um MacroSummary.
    """
    return MacroSummary(
        protein_g=round(sum(m["protein_g"] for m in macros_list), 2),
        carbs_g=round(sum(m["carbs_g"] for m in macros_list), 2),
        fats_g=round(sum(m["fats_g"] for m in macros_list), 2),
        kcal=round(sum(m["kcal"] for m in macros_list), 2)
    )

def _build_adherence(plan: MealPlan, actuals: MacroSummary) -> Optional[MacroAdherence]:
    """
    Constrói o resumo de adherence (real vs target).
    Retorna None se o plano não tiver targets definidos.
    """

    has_targets = any([
        plan.kcal_target,
        plan.protein_target_g,
        plan.carbs_target_g,
        plan.fats_target_g,
    ])
    if not has_targets:
        return None
    
    def diff(actual_val:float, target:Optional[float]) -> Optional[float]:
        #Calcula a diferença entre valor real e target. Retorna None se o target for None.
        return round(actual_val - target, 2) if target is not None else None
    
    return MacroAdherence(
        kcal_target=plan.kcal_target,
        kcal_actual=actuals.kcal,
        kcal_diff=diff(actuals.kcal, plan.kcal_target),

        protein_target_g=plan.protein_target_g,
        protein_actual=actuals.protein_g,
        protein_diff_g=diff(actuals.protein_g, plan.protein_target_g),

        carbs_target_g=plan.carbs_target_g,
        carbs_actual=actuals.carbs_g,
        carbs_diff_g=diff(actuals.carbs_g, plan.carbs_target_g),

        fats_target_g=plan.fats_target_g,
        fats_actual=actuals.fats_g,
        fats_diff_g=diff(actuals.fats_g, plan.fats_target_g),
    )

#===================================
#MealPlan CRUD
#===================================

def get_meal_plan_by_id(session: Session, meal_plan_id: int) -> Optional[MealPlan]:
    return session.get(MealPlan, meal_plan_id)

def list_meal_plans_by_client(session: Session, client_id: str, include_archived: bool = False) -> List[MealPlan]:
    """
    Lista os planos alimentares de um cliente.
    """
    stmt = (
        select(MealPlan)
        .where(MealPlan.client_id == client_id)
        .order_by(MealPlan.created_at.desc())
    )
    if not include_archived:
        stmt = stmt.where(MealPlan.archived_at.is_(None))
        return session.exec(stmt).all()
    
def deactivate_client_plans(session: Session, client_id: str) -> None:
    """
    Desativa todos os planos ativos de um cliente.
    Chamado antes de criar um novo plano para garantir que só exista um plano ativo por cliente por dia.
    """
    stmt = select(MealPlan).where(
        MealPlan.client_id == client_id,
        MealPlan.active == True,
        MealPlan.archived_at.is_(None),
    )
    active_plans = session.exec(stmt).all()
    for plan in active_plans:
        plan.active = False
        plan.archived_at = datetime.now(timezone.utc)
        session.add(plan)

def create_meal_plan(session: Session, payload: MealPlanCreate) -> MealPlan:
    """
    Cria um plano alimentar.
    Se active=True, desativa os planos anteriores do cliente primeiro.
    O flush() é usado entre criações para propagar os IDs gerados.
    (commit é feito no router)
    """
    #Se este plano vai ser ativo, desativa os planos anteriores do cliente primeiro para garantir que só exista um plano ativo por cliente por dia.
    if payload.active:
        deactivate_client_plans(session, payload.client_id)

    #cria o cabeçalho do plano
    meal_plan = MealPlan(
        client_id=payload.client_id,
        name=payload.name,
        starts_date=payload.starts_date,
        ends_date=payload.ends_date,
        active=payload.active,
        notes=payload.notes,
    )
    session.add(meal_plan)
    session.flush() #propaga o ID do meal_plan para as refeições

    #cria cada refeição e seus alimentos
    for meal_payload in payload.meals:
        meal = MealPlanMeal(
            meal_plan_id=meal_plan.id,
            name=meal_payload.name,
            order_index=meal_payload.order_index,
        )
        session.add(meal)
        session.flush() #propaga o ID da meal para os itens

        for item_payload in meal_payload.items:
            item = MealPlanItem(
                meal_plan_meal_id=meal.id,
                food_id=item_payload.food_id,
                quantity_grams=item_payload.quantity_grams,
            )
            session.add(item)
    return meal_plan

def update_meal_plan(session: Session, meal_plan: MealPlan, payload: MealPlanUpdate) -> MealPlan:
    """
    Atualiza um plano alimentar.
    Se active=True, desativa os planos anteriores do cliente primeiro.
    """
    #Se este plano vai ser ativo, desativa os planos anteriores do cliente primeiro para garantir que só exista um plano ativo por cliente por dia.
    if payload.active is True and not meal_plan.active:
        deactivate_client_plans(session, meal_plan.client_id)

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(meal_plan, key, value)
    meal_plan.updated_at = datetime.now(timezone.utc)
    session.add(meal_plan)
    return meal_plan

def soft_delete_meal_plan(session: Session, meal_plan: MealPlan) -> MealPlan:
    """
    "Deleta" um plano alimentar marcando-o como inativo e definindo archived_at.
    """
    meal_plan.archived_at = datetime.now(timezone.utc)
    meal_plan.active = False
    meal_plan.updated_at= datetime.now(timezone.utc)
    session.add(meal_plan)
    return meal_plan

#===================================
#Leitura com macros agregados
#===================================

def build_meal_plan_read(session: Session, meal_plan: MealPlan) -> MealPlanRead:
    """
    Constrói MealPlanRead completo:
      - Carrega todas as refeições e items numa passagem
      - Calcula macros em Python (sem N+1)
      - Calcula adherence se targets estiverem definidos
      - Adiciona label legível para plan_type
    """
    #Carrega todas as refeções do plano, ordenadas
    meals_orm = session.exec(
        select(MealPlanMeal)
        .where(MealPlanMeal.meal_plan_id == meal_plan.id)
        .order_by(MealPlanMeal.order_index)
    ).all()

    plan_macros_list: List[dict] = []
    meals_read: List[MealPlanMealRead] = []

    for meal in meals_orm:
        #Carrega os itens de cada refeição
        items_orm = session.exec(
            select(MealPlanItem)
            .where(MealPlanItem.meal_plan_meal_id == meal.id)
        ).all()

        meal_macros_list: List[dict] = []
        items_read: List[MealPlanItemRead] = []

        for item in items_orm:
            food = session.get(Food, item.food_id)
            if food is None:
                continue #pula itens com alimentos inexistentes (dados inconsistente)

            #calcula as macros para esta quantidade do alimento
            item_macros = _calculate_item_macros(food, item.quantity_grams)

            items_read.append(
                MealPlanItemRead(
                    id=item.id,
                    food_id=food.id,
                    food_name=food.name, #desnormalização para facilitar leitura no front end
                    quantity_grams=item.quantity_grams,
                    **item_macros,
                )
            )

            meal_macros_list.append(item_macros)

        #Agrega macros da refeição
        meal_macros_summary = _sum_macros(meal_macros_list)
        plan_macros_list.append(meal_macros_summary)

        meals_read.append(
            MealPlanMealRead(
                id=meal.id,
                name=meal.name,
                order_index=meal.order_index,
                items=items_read,
                meal_macros=meal_macros_summary,
            )
        )

    #agrega macros totais do plano
    plan_macro_summary = _sum_macros(plan_macros_list)
    adherence    = _build_adherence(meal_plan, plan_macro_summary)

    #Label legível para plan_type
    plan_type_label = PLAN_TYPE_OPTIONS.get(meal_plan.plan_type) if meal_plan.plan_type else None
    
    return MealPlanRead(
        id=meal_plan.id,
        client_id=meal_plan.client_id,
        name=meal_plan.name,
        plan_type=meal_plan.plan_type,
        plan_type_label=plan_type_label,
        starts_date=meal_plan.starts_date,
        ends_date=meal_plan.ends_date,
        active=meal_plan.active,
        notes=meal_plan.notes,
        kcal_target=meal_plan.kcal_target,
        carbs_target_g=meal_plan.carbs_target_g,
        protein_target_g=meal_plan.protein_target_g,
        fats_target_g=meal_plan.fats_target_g,
        meals=meals_read,
        plan_macros=plan_macro_summary,
        adherence=adherence,
        archived_at=meal_plan.archived_at,
        created_at=meal_plan.created_at,
        updated_at=meal_plan.updated_at,
    )