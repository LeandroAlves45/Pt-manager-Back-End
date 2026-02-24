from datetime import datetime, date
from typing import Optional, List, Literal
from pydantic import BaseModel, field_validator, model_validator
from sqlmodel import SQLModel, Field

from app.db.models.nutrition import PLAN_TYPE_OPTIONS
from app.services.macro_calculator import ACTIVITY_FACTORS

#---------------------------------------------
#Food
#---------------------------------------------

class FoodCreate(SQLModel):
    """
    Payload para criação de um novo alimento.
    """

    name: str = Field(min_length=1, max_length=100)
    carbs: float = Field(ge=0, le=100.0)
    protein: float = Field(ge=0, le=100.0)
    fats: float = Field(ge=0, le=100.0)

    @model_validator(mode="after")
    def validate_macros_sum(self) -> "FoodCreate":
        """
        Valida se a soma de carboidratos, proteínas e gorduras não excede 100g por porção.
        Tolerância de 1gr para arredondamento.
        """
        total = (self.carbs or 0) + (self.protein or 0) + (self.fats or 0)
        if total > 101.0:
            raise ValueError(f"Soma das macros ({total:.1f}g) não pode exceder 100g por 100gr de alimento.")
        return self
    
class FoodUpdate(SQLModel):
    """
    Payload para atualização de um alimento.
    Todos os campos são opcionais.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    carbs: Optional[float] = Field(default=None, ge=0, le=100.0)
    protein: Optional[float] = Field(default=None, ge=0, le=100.0)
    fats: Optional[float] = Field(default=None, ge=0, le=100.0)
    is_active: Optional[bool] = None

class FoodRead(BaseModel):
    #Schema para leitura de um alimento.
    id: int
    name: str
    carbs: float
    protein: float
    fats: float
    kcal: Optional[float] 
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

#---------------------------------------------
#MacroSummary - Resumo de macros para um dia. Calculado via query customizada. Nunca armazenado diretamente.
#---------------------------------------------

class MacroSummary(BaseModel):
    """
    Resumo de macros calculado via query agregada.
    Não corresponde a nenhuma tabela - é construido no crud
    """

    protein_g: float
    carbs_g: float
    fats_g: float
    kcal: float

class MacroAdherence(BaseModel):
    """
    Comparação entre macros reais (alimentos do plano) e targets do PT.
    Ajuda o PT a ver de relance se o plano está alinhado com os objetivos.
    Apenas calculado quando o plano tem targets definidos.
    """

    kcal_target: Optional[float]
    kcal_actual: float
    kcal_diff: Optional[float] # real-target (negativo = abaixo)

    protein_target_g: Optional[float]
    protein_actual_g: float
    protein_diff_g: Optional[float] # real-target (negativo = abaixo)

    carbs_target_g: Optional[float]
    carbs_actual_g: float
    carbs_diff_g: Optional[float] # real-target (negativo = abaixo)

    fats_target_g: Optional[float]
    fats_actual_g: float
    fats_diff_g: Optional[float] # real-target (negativo = abaixo)

#---------------------------------------------
# Schemas de cálculo de macros
#---------------------------------------------

class MacroCalculationRequest(BaseModel):
    """
    Input para calcular TMB e distribuição de macros.

    Fluxo de uso:
      1. PT preenche dados biométricos do cliente + fator de atividade
      2. API devolve TMB/TDEE pelas 3 fórmulas
      3. PT escolhe o TDEE que quer usar e define as % de macros
      4. API devolve as gramas correspondentes
      5. PT usa esses valores para preencher os targets do MealPlan
    """

    #Dados biométricos
    weight_kg: float = Field(ge=20.0, le=500.0, description="Peso do cliente em kg")
    height_cm: float = Field(ge=50.0, le=300.0, description="Altura do cliente em cm")
    age: int = Field(ge=5, le=120, description="Idade do cliente em anos")
    sex: Literal["male", "female"] = Field(description="Sexo do cliente")

    #Fator de atividade física
    activity_key: str = Field(
        description=(
            "Nível de atividade física."
                    "Valores: sedentary | lightly_active | moderately_active | very_active | extremely_active"
        )
    )

    #Calorias alvo definidas pelo PT com base no TDEE escolhido
    kcal_target: Optional[float] = Field(default=None, ge=0, le=15000.0, description="Total calórico diário escolhido pelo PT (kcal)")

    #Percentagens de macros definidas pelo PT (soma deve ser 100%)
    protein_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0, description="% de proteínas")
    carbs_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0, description="% de carboidratos")
    fats_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0, description="% de gorduras")

    @field_validator("activity_key")
    def validate_activity_key(cls, v: str) -> str:
        if v not in ACTIVITY_FACTORS:
            raise ValueError(f"activity_key inválido. Deve ser um dos seguintes: {', '.join(ACTIVITY_FACTORS.keys())}")
        return v
    
    @model_validator(mode="after")
    def validate_macros_pct_consitency(self) -> "MacroCalculationRequest":
        """
        Se kcal_target for enviado, as 3 percentagens são obrigatórias.
        Se não for enviado, as percentagens são ignoradas.
        """

        has_kcal = self.kcal_target is not None
        has_pct = all(p is not None for p in [self.protein_pct, self.carbs_pct, self.fats_pct])
        if has_kcal and not has_pct:
            raise ValueError("Se kcal_target for enviado, protein_pct, carbs_pct e fats_pct são obrigatórios.")
        return self
    
class FormulaResult(BaseModel):
    """
    Resultado do cálculo de TMB/TDEE por uma fórmula específica.
    """

    formula: str #nome da fórmula usada, ex: "harris_benedict", "mifflin_st_jeor", "katch_mcardle"
    label: str #rótulo amigável para a fórmula, ex: "Harris-Benedict (1984)"
    tmb: float #TMB calculada pela fórmula
    tdee: float #TDEE calculado pela fórmula (TMB multiplicada pelo fator de atividade)

class MacroDistribution(BaseModel):
    """
    Distribuição de macros calculada pelo serviço.
    Devolve sempre as gramas absolutas + g/kg + percentagens,
    independente do método usado — para o PT ter todas as referências.
    """
    method: str #indica se a distribuição foi calculada a partir de percentagens ou de g/kg
    kcal_target: float

    #Percentagens das kcal totais
    protein_pct: float
    carbs_pct: float
    fats_pct: float

    #Resultados em gramas totais
    protein_g: float
    carbs_g: float
    fats_g: float

    # Total calórico que resulta dos macros definidos
    # Pode diferir de kcal_target (especialmente com method="g_per_kg")
    kcal_from_macros: float 


    #Referências clinicas - calculadas sempre
    protein_g_per_kg: float #proteínas em gramas por kg de peso corporal
    carbs_g_per_kg: float #carbs em gramas por kg de peso corporal
    fats_g_per_kg: float #gorduras em gramas por kg de peso

class MacroCalculationResponse(BaseModel):
    """
    Resposta do endpoint de cálculo de macros, incluindo TMB/TDEE pelas 3 fórmulas e a distribuição de macros escolhida pelo PT.
    """
    #Dados de entrada confirmados
    weight_kg: float
    height_cm: float
    age: int
    sex: str
    activity_key: str
    activity_label: str
    activity_factor : float

    #Resultados das fórmulas de TMB/TDEE
    formulas: List[FormulaResult]

    #distribuição de macros - None se não foram enviadas percentagens
    macro_distribution: Optional[MacroDistribution] = None 

#---------------------------------------------
#MealPlanItem - Item do plano alimentar
#---------------------------------------------

class MealPlanItemCreate(BaseModel):
    """
    Payload para criação de um item do plano alimentar.
    """

    food_id: int
    quantity_grams: float = Field(ge=1.0, le=7000.0)

class MealPlanItemRead(BaseModel):
    #Schema para leitura de um item do plano alimentar.
    id: int
    food_id: int
    food_name: str #denormalizado para facilitar leitura
    quantity_grams: float

    #macros denormalizados para facilitar leitura - calculados no crud
    carbs_g: float
    protein_g: float
    fats_g: float
    kcal: float

    class Config:
        from_attributes = True

#---------------------------------------------
#Macro Targets - Targets de macros definidos pelo PT para o plano alimentar. Calculados a partir do MacroCalculationResponse.
#---------------------------------------------
class MacroTargets(BaseModel):
    """
    Sub-schema para definir os targets de macros num plano.
    O PT preenche depois de ver os resultados de /calculate-macros.
    """
    kcal_target: float = Field(ge=0, le=15000.0)
    protein_target_g: float = Field(ge=0.0)
    carbs_target_g: float = Field(ge=0.0)
    fats_target_g: float = Field(ge=0.0)


#---------------------------------------------
#MealPlanMeal 
#---------------------------------------------

class MealPlanMealCreate(BaseModel):
    """
    Payload para criação de uma refeição dentro do plano alimentar.
    """

    name: str = Field(min_length=1, max_length=100)
    order_index: int = Field(default=0, ge=0)
    items: List[MealPlanItemCreate] = Field(default_factory=list)

class MealPlanMealRead(BaseModel):
    #Schema para leitura de uma refeição do plano alimentar, incluindo seus itens.
    id: int
    name: str
    order_index: int
    items: List[MealPlanItemRead]
    meal_macros: MacroSummary #macros agregados da refeição, calculados no crud

    class Config:
        from_attributes = True

#---------------------------------------------
#MealPlan - Plano alimentar
#---------------------------------------------

class MealPlanCreate(BaseModel):
    """
    Payload para criação de um plano alimentar.
    """
    client_id: str
    name: str = Field(min_length=1, max_length=100)
    starts_date: Optional[date] = None
    ends_date: Optional[date] = None
    active: bool = True
    notes: Optional[str] = None
    meals: List[MealPlanMealCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dates(self) -> "MealPlanCreate":
        #Garante que a data de início não seja posterior à data de término, se ambas forem fornecidas.
        if self.starts_date and self.ends_date:
            if self.ends_date < self.starts_date:
                raise ValueError("starts_date não pode ser posterior a ends_date.")
        return self
    
class MealPlanUpdate(BaseModel):
    #Atualização parcial do plano alimentar. Todos os campos opcionais.
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    starts_date: Optional[date] = None
    ends_date: Optional[date] = None
    active: Optional[bool] = None
    notes: Optional[str] = None

class MealPlanRead(BaseModel):
    #Schema para leitura de um plano alimentar, incluindo suas refeições e itens.
    id: int
    client_id: str
    name: str
    starts_date: Optional[date]
    ends_date: Optional[date]
    active: bool
    notes: Optional[str]
    meals: List[MealPlanMealRead]
    plan_macros: MacroSummary #macros agregados do plano, calculados no crud

    archived_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

