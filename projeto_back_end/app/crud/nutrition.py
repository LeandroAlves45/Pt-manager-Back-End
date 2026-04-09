"""
CRUD para o sistema de nutrição.

Responsabilidades:
- Queries à BD para alimentos, planos alimentares, refeições e itens do plano
- create_meal_plan / update_meal_plan lidam com targets de macros
- build_meal_plan_read calcula 'adherence' quando targets estão definidos
- Nunca levanta HTTPException — isso é responsabilidade dos routers
"""



from datetime import datetime,timezone
from typing import List, Optional

from sqlmodel import Session, select
from app.db.models.nutrition import (
    Food, 
    MealPlan, 
    MealPlanMeal, 
    MealPlanItem, 
    MealPlanMealSupplement, 
    PLAN_TYPE_OPTIONS,
)
from app.schemas.nutrition import (
    FoodCreate,
    FoodUpdate,
    MealPlanItemRead,
    MacroSummary,
    MealPlanMealRead,
    MealPlanUpdate,
    MealPlanCreate,
    MealPlanRead,
    MacroAdherence,
    MealPlanMealsUpdate,
    MealPlanMealSupplementRead,
)

#===================================
#FOOD CRUD
#===================================

def get_food_by_id(session: Session, food_id: str) -> Optional[Food]:
    return session.get(Food, food_id)

def list_foods(
    session: Session, 
    trainer_id: str,
    active_only:bool = True, 
    limit: int = 200,
) -> List[Food]:
    """
    Lista alimentos visíveis para o Personal Trainer:
        - Alimentos globais (owner_trainer_id IS NULL)
        - Alimentos privados do Personal Trainer (owner_trainer_id == trainer_id)

    Esta query é o ponto crítico de multi-tenancy para foods:
    sem o filtro de tenant, o Personal Trainer A veria os alimentos privados do Personal Trainer B.
    """
    stmt = select(Food).where(
        (Food.owner_trainer_id.is_(None)) | (Food.owner_trainer_id == trainer_id)
    )

    if active_only:
        stmt =stmt.where(Food.is_active == True)
    stmt = stmt.order_by(Food.name)
    stmt = stmt.limit(limit)
    return session.exec(stmt).all()

def create_food(
    session: Session, 
    payload: FoodCreate, 
    owner_trainer_id: str,
) -> Food:
    """
    Cria um alimento privado para o Personal Trainer.
    owner_trainer_id é sempre o ID do Personal Trainer — alimentos privados nunca ficam None.
    Alimentos globais são criados pela seed do catálogo, não por este endpoint.
    """
    
    food = Food(
        name=payload.name,
        carbs=payload.carbs,
        protein=payload.protein,
        fats=payload.fats,
        owner_trainer_id=owner_trainer_id,
    )
    session.add(food)
    return food

def update_food(
    session: Session, 
    food: Food, 
    payload: FoodUpdate,
) -> Food:
    """
    Actualiza os campos de um alimento.
    kcal não está no payload — é recalculada automaticamente pelo PostgreSQL
    via coluna GENERATED (carbs*4 + protein*4 + fats*9).
    """

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
    """
    Calcula os macros de um item do plano alimentar baseado no alimento e quantidade.
 
    Fórmula: macro_real = (macro_por_100g / 100) * quantity_grams
 
    O cálculo é feito em Python (não no SQL) para manter flexibilidade:
    permite ajustes futuros (ex: factor de cozedura, rastreio de micronutrientes)
    sem necessitar de alterar a BD.
    """

    factor = quantity_grams / 100.0
    protein = round((food.protein or 0) * factor, 2)
    carbs=round((food.carbs or 0) * factor, 2)
    fats=round((food.fats or 0) * factor, 2)
    kcal=round(protein * 4 + carbs * 4 + fats * 9, 2)
    return {"protein_g": protein, "carbs_g": carbs, "fats_g": fats, "kcal": kcal}

def _sum_macros(macros_list: List[dict]) -> MacroSummary:
    """
    Agrega uma lista de macros (dicts ou MacroSummary) num único MacroSummary.
    Usado para totalizar macros por refeição e por plano completo.
    """

    def _get(item, key):
        # Suporta tanto dicts quanto MacroSummary (que tem os campos como atributos)
        return getattr(item, key, None) or (item.get(key) if isinstance(item, dict) else 0)
    
    return MacroSummary(
        protein_g=round(sum(_get(m, "protein_g") for m in macros_list), 2),
        carbs_g=round(sum(_get(m, "carbs_g") for m in macros_list), 2),
        fats_g=round(sum(_get(m, "fats_g") for m in macros_list), 2),
        kcal=round(sum(_get(m, "kcal") for m in macros_list), 2)
    )

def _build_adherence(plan: MealPlan, actuals: MacroSummary) -> Optional[MacroAdherence]:
    """
    Constrói o resumo de adherence (real vs target).
    Retorna None se o plano não tiver targets definidos.
    """

    has_targets = any([
        plan.kcal_target,
        plan.protein_target,
        plan.carbs_target,
        plan.fats_target,
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

        protein_target_g=plan.protein_target,
        protein_actual_g=actuals.protein_g,
        protein_diff_g=diff(actuals.protein_g, plan.protein_target),

        carbs_target_g=plan.carbs_target,
        carbs_actual_g=actuals.carbs_g,
        carbs_diff_g=diff(actuals.carbs_g, plan.carbs_target),

        fats_target_g=plan.fats_target,
        fats_actual_g=actuals.fats_g,
        fats_diff_g=diff(actuals.fats_g, plan.fats_target),
    )

#===================================
#MealPlan CRUD
#===================================

def get_meal_plan_by_id(session: Session, meal_plan_id: str) -> Optional[MealPlan]:
    """Busca um plano alimentar por UUID."""
    return session.get(MealPlan, meal_plan_id)

def list_meal_plans_by_client(
        session: Session, 
        client_id: str, 
        include_archived: bool = False,
) -> List[MealPlan]:
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
    
    NÃO é chamada automaticamente — o Personal Trainer pode ter múltiplos planos
    ativos em simultâneo. Esta função fica disponível para uso
    explícito no futuro se necessário.
    """

    stmt = select(MealPlan).where(
        MealPlan.client_id == client_id,
        MealPlan.active == True,
        MealPlan.archived_at.is_(None),
    )
    active_plans = session.exec(stmt).all()

    for plan in active_plans:
        plan.active = False
        session.add(plan)

    if active_plans:
        session.flush()

def _create_meal_supplements(
    session: Session,
    meal_id: str,
    supplements: list,
) -> None:
    """
    Cria as associações entre uma refeição e os seus suplementos (NR-04).

    Chamado internamente por create_meal_plan e replace_meal_plan_meals.
    Ignora supplements vazios silenciosamente — refeições sem suplementos
    são válidas e não exigem tratamento especial.

    Os suplementos inválidos são validados no router antes de chegar aqui.
    """

    for supp_item in supplements:
        assoc = MealPlanMealSupplement(
            meal_plan_meal_id=meal_id,
            supplement_id=supp_item.supplement_id,
            notes=supp_item.notes,
        )
        session.add(assoc)

def create_meal_plan(
        session: Session, 
        payload: MealPlanCreate,
        trainer_id: str,
    ) -> MealPlan:
    """
    Cria um plano alimentar.
    Regras:
        Um cliente pode ter vários planos alimentares ativos (dias altos, baixos, etc) — o Personal Trainer decide como gerir isso.
    """

    #cria o cabeçalho do plano
    meal_plan = MealPlan(
        client_id=payload.client_id,
        owner_trainer_id=trainer_id,
        name=payload.name,
        starts_date=payload.starts_date,
        ends_date=payload.ends_date,
        active=payload.active,
        notes=payload.notes,
        kcal_target=payload.kcal_target,
        protein_target=payload.protein_target_g,
        carbs_target=payload.carbs_target_g,
        fats_target=payload.fats_target_g,
    )
    session.add(meal_plan)
    session.flush() # propaga o ID do meal_plan para as refeições

    #cria cada refeição e seus alimentos
    for idx, meal_payload in enumerate(payload.meals):
        meal = MealPlanMeal(
            meal_plan_id=meal_plan.id,
            name=meal_payload.name,
            order_index=meal_payload.order_index if meal_payload.order_index is not None else idx, #se order_index não for fornecido, usa a ordem do payload
        )
        session.add(meal)
        session.flush() # propaga o ID da meal para os itens

        for item_payload in meal_payload.items:
            item = MealPlanItem(
                meal_id=meal.id,
                food_id=item_payload.food_id,
                quantity_grams=item_payload.quantity_grams,
            )
            session.add(item)
        session.flush()  # propaga os items antes de criar suplementos

        if meal_payload.supplements:
            _create_meal_supplements(session, meal.id, meal_payload.supplements)
    return meal_plan

def update_meal_plan(session: Session, meal_plan: MealPlan, payload: MealPlanUpdate) -> MealPlan:
    """
    Atualiza os metadados de um plano alimentar (não as refeições).
    """

    data = payload.model_dump(exclude_unset=True)

    # Remapeia campos _g do schema para os nomes do modelo ORM
    field_map = {
        "protein_target_g": "protein_target",
        "carbs_target_g": "carbs_target",
        "fats_target_g": "fats_target",
    }

    remapped = {}

    for key, value in data.items():
        orm_key = field_map.get(key, key)  # remapeia se necessário, senão mantém o mesmo nome
        remapped[orm_key] = value

    for key, value in remapped.items():
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

def unarchive_meal_plan(session: Session, meal_plan: MealPlan) -> MealPlan:

    """
    Reverte o arquivamento de um plano alimentar:
      - archived_at → None  (plano volta a aparecer na lista de ativos)
      - active → True       (plano fica imediatamente ativo)
      - updated_at → agora
    """

    meal_plan.archived_at = None
    meal_plan.active = True
    meal_plan.updated_at = datetime.now(timezone.utc)
    session.add(meal_plan)
    return meal_plan


def replace_meal_plan_meals(
    session: Session,
    meal_plan: MealPlan,
    payload: MealPlanMealsUpdate,
) -> MealPlan:
    """
    Substitui todas as refeicoes e items de um plano pela nova lista.
 
    Estratégia delete-and-replace:
      1. Remove explicitamente todos os MealPlanMealSupplement
      2. Remove todos os MealPlanItem
      3. Remove todos os MealPlanMeal
      4. Recria as refeições, itens e associações de suplementos
 
    O commit e feito no router (separacao de responsabilidades).
    """
    # Carrega todas as refeições existentes do plano
    existing_meals = session.exec(
        select(MealPlanMeal)
        .where(MealPlanMeal.meal_plan_id == meal_plan.id)
    ).all()
    
    # Passo 1: eliminar explicitamente todas as associações de suplementos
    for meal in existing_meals:
        supplement_assocs = session.exec(
            select(MealPlanMealSupplement)
            .where(MealPlanMealSupplement.meal_plan_meal_id == meal.id)
        ).all()
        for assoc in supplement_assocs:
            session.delete(assoc)

    session.flush()  # propaga os deletes antes de remover as refeicoes
 
    # Passo 2:eliminar todos os items  de todas as refeições
    for meal in existing_meals:
        items = session.exec(
            select(MealPlanItem)
            .where(MealPlanItem.meal_id == meal.id)
        ).all()
        for item in items:
            session.delete(item)
            
    session.flush()  # propaga antes de criar as novas
 
    # Passo 3: eliminar as refeições (CASCADE na BD trata o resto)
    for meal in existing_meals:
        session.delete(meal)
    session.flush()  # propaga antes de criar as novas

    # Passo 4: Recriar refeições, items e associações de suplementos a partir do payload
    for idx, meal_payload in enumerate(payload.meals):
        meal = MealPlanMeal(
            meal_plan_id=meal_plan.id,
            name=meal_payload.name,
            order_index=meal_payload.order_index if meal_payload.order_index is not None else idx,
        )
        session.add(meal)
        session.flush()  # obtem o ID da nova refeicao
 
        for item_payload in meal_payload.items:
            item = MealPlanItem(
                meal_id=meal.id,
                food_id=item_payload.food_id,
                quantity_grams=item_payload.quantity_grams,
            )
            session.add(item)
        session.flush()  # propaga os items antes de criar suplementos

        if meal_payload.supplements:
            _create_meal_supplements(session, meal.id, meal_payload.supplements)
 
    meal_plan.updated_at = datetime.now(timezone.utc)
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
            .where(MealPlanItem.meal_id == meal.id)
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

        supplements_orm = session.exec(
            select(MealPlanMealSupplement)
            .where(MealPlanMealSupplement.meal_plan_meal_id == meal.id)
        ).all()

        from app.db.models.supplement import Supplement as SupplementModel
        supplements_read = []
        for assoc in supplements_orm:
            supplement = session.get(SupplementModel, assoc.supplement_id)
            if supplement is None:
                continue #pula suplementos inexistentes (dados inconsistentes)

            supplements_read.append(
                MealPlanMealSupplementRead(
                    id=assoc.id,
                    supplement_id=supplement.id,
                    supplement_name=supplement.name, #desnormalização para facilitar leitura no front end
                    supplement_timing=supplement.timing,
                    notes=assoc.notes,
                )
            )

        meals_read.append(
            MealPlanMealRead(
                id=meal.id,
                name=meal.name,
                order_index=meal.order_index,
                items=items_read,
                meal_macros=meal_macros_summary,
                supplements=supplements_read,
            )
        )

    #agrega macros totais do plano
    plan_macro_summary = _sum_macros(plan_macros_list)
    adherence = _build_adherence(meal_plan, plan_macro_summary)

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
        protein_target_g=meal_plan.protein_target,
        carbs_target_g=meal_plan.carbs_target,
        fats_target_g=meal_plan.fats_target,
        meals=meals_read,
        plan_macros=plan_macro_summary,
        adherence=adherence,
        archived_at=meal_plan.archived_at,
        created_at=meal_plan.created_at,
        updated_at=meal_plan.updated_at,
    )