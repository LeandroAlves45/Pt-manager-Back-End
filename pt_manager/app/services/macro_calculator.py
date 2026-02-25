"""
Serviço de cálculo de macros e Taxa Metabólica Basal (TMB).

Este módulo é PURO — não acede à base de dados nem ao FastAPI.
Recebe dados, executa cálculos matemáticos, devolve resultados.
Pode ser testado de forma completamente isolada.

Fórmulas implementadas:
  - Harris-Benedict (revisão Roza & Shizgal, 1984)
  - Mifflin-St Jeor (1990) — considerada a mais precisa para a população geral
  - Waldemar (formula de referência usada em contexto desportivo PT/BR)

Fatores de Atividade Física (PAL — Physical Activity Level):
  Sedentário         1.200 — escritório, sem exercício
  Pouco ativo        1.375 — exercício leve 1-3x/semana
  Moderadamente      1.550 — exercício moderado 3-5x/semana
  Muito ativo        1.725 — exercício intenso 6-7x/semana
  Extremamente ativo 1.900 — trabalho físico diário + treino bidiário

Distribuição de macros:
  O PT define as percentagens manualmente.
  Conversão: 1g proteína = 4 kcal, 1g hidratos = 4 kcal, 1g gordura = 9 kcal
"""

from dataclasses import dataclass
from typing import Literal
from math import isclose



#---------------------------------------------
#Constantes
#---------------------------------------------

#Fatores de Atividade Física (PAL)
ACTIVITY_FACTORS: dict[str, float] = {
    "sedentary": 1.200, #sedentário
    "lightly_active": 1.375, #pouco ativo
    "moderately_active": 1.550, #moderadamente ativo
    "very_active": 1.725, #muito ativo
    "extremely_active": 1.900, #extremamente ativo
}

#Kcal por grama de cada macronutriente
KCAL_PER_GRAM_PROTEIN = 4.0
KCAL_PER_GRAM_CARBS = 4.0
KCAL_PER_GRAM_FATS = 9.0

#---------------------------------------------
#Tipos personalizados
#---------------------------------------------

SexType = Literal["male", "female"]

@dataclass(frozen=True)
class TmbResult:
    """
    Resultado de uma fórmula TMB.
    frozen=True torna o objeto imutável após criação (boas práticas).
    """
    formula: str #nome da fórmula usada (ex: "Mifflin-St Jeor")
    label: str #rótulo legível para o usuário (ex: "Mifflin-St Jeor (1990)")
    tmb: float #valor da TMB em kcal/dia
    tdee: float #valor da TDEE em kcal/dia (TMB x fator de atividade)   

@dataclass(frozen=True)
class MacroGrams:
    """
    Quantidades de macronutrientes em gramas.
    """
    protein_g: float
    carbs_g: float
    fats_g: float
    kcal_total: float #confirmação do total real 
    protein_g_per_kg: float #quantidade de proteína por kg de peso corporal
    carbs_g_per_kg: float #quantidade de carboidratos por kg de peso corporal
    fats_g_per_kg: float #quantidade de gorduras por kg de peso corporal
    protein_pct: float #percentagem de calorias provenientes de proteínas (informativo)
    carbs_pct: float #percentagem de calorias provenientes de carboidratos (informativo)
    fats_pct: float  #percentagem de calorias provenientes de gorduras (informativo)

#---------------------------------------------
# Fórmulas de cálculo de TMB 
#---------------------------------------------

def _harris_benedict(weight_kg: float, height_cm: float, age: int, sex: SexType) -> float:
    """
    Harris-Benedict (revisão Roza & Shizgal, 1984).

    Homem:  88.362 + (13.397 × peso) + (4.799 × altura) − (5.677 × idade)
    Mulher: 447.593 + (9.247 × peso) + (3.098 × altura) − (4.330 × idade)
    """

    if sex == "male":
        return 88.362 + (13.397 * weight_kg) + (4.799 * height_cm) - (5.677 * age)
    else:
        return 447.593 + (9.247 * weight_kg) + (3.098 * height_cm) - (4.330 * age)
    

def _mifflin_st_jeor(weight_kg: float, height_cm: float, age: int, sex: SexType) -> float:
    """
    Mifflin-St Jeor (1990) — considerada a mais precisa para a população geral.

    Homem:  (10 × peso) + (6.25 × altura) − (5 × idade) + 5
    Mulher: (10 × peso) + (6.25 × altura) − (5 × idade) − 161
    """
    base= (10 * weight_kg) + (6.25 * height_cm) - (5 * age)
    return base + 5 if sex == "male" else base - 161

def _waldemar(weight_kg: float, height_cm: float, age: int, sex: SexType) -> float:
    """
    Fórmula de Waldemar.
    
    Variante implementada (usada em contexto PT/BR desportivo):
    Homem:  (13.7 × peso) + (5.0 × altura) − (6.8 × idade) + 66
    Mulher: (9.6 × peso)  + (1.8 × altura) − (4.7 × idade) + 655
    (Equivalente à fórmula de Harris-Benedict original de 1919 — "Waldemar" no meio desportivo refere frequentemente esta versão original)
    """
    if sex == "male":
        return (13.7 * weight_kg) + (5.0 * height_cm) - (6.8 * age) + 66
    else:
        return (9.6 * weight_kg) + (1.8 * height_cm) - (4.7 * age) + 655
    
#---------------------------------------------
# função principal - calcula TMB/TDEE pelas 3 fórmulas
#---------------------------------------------

def calculate_tmb_all_formulas(
    weight_kg: float,
    height_cm: float,
    age: int,
    sex: SexType,
    activity_key: str,
) -> list[TmbResult]:
    """
    Calcula a TMB e o TDEE pelas 3 fórmulas.

    Parâmetros:
        weight_kg     — peso em kg
        height_cm     — altura em cm
        age           — idade em anos
        sex           — 'male' ou 'female'
        activity_key  — chave do fator de atividade (ex: 'very_active')

    Devolve:
        Lista de TmbResult com os resultados de cada fórmula,
        ordenada por TDEE crescente.

    Levanta:
        ValueError se activity_key não for válido.
    """
    if activity_key not in ACTIVITY_FACTORS: 
        valid = ", ".join(ACTIVITY_FACTORS.keys())
        raise ValueError(f"activity_key inválida. Deve ser um dos: {valid}")

    activity_factor = ACTIVITY_FACTORS[activity_key]

    #calcula TMB para cada fórmula
    formulas = [
        ("Harris-Benedict", "Harris-Benedict (1984)", _harris_benedict),
        ("Mifflin-St Jeor", "Mifflin-St Jeor (1990)", _mifflin_st_jeor),
        ("Waldemar", "Waldemar (1919)", _waldemar),
    ]
    results = []
    for key, label, formula in formulas:
        tmb = round(formula(weight_kg, height_cm, age, sex),1)
        tdee = round(tmb * activity_factor,1)

        results.append(TmbResult(formula=key, label=label, tmb=tmb, tdee=tdee))

    #ordena por TDEE crescente
    results.sort(key=lambda x: x.tdee)
    return results
#---------------------------------------------
# Distribuição de macros a partir de calorias  + percentagens manuais
#---------------------------------------------

def calculate_macros_from_percentages (
        kcal_target: float,
        protein_pct: float,
        carbs_pct: float,
        fats_pct: float,
        weight_kg: float,
) -> MacroGrams:
    """
    Calcula a quantidade de macros em gramas a partir de um objetivo calórico e percentagens.

    Parâmetros:
        kcal_target  — objetivo calórico total (kcal/dia)
        protein_pct  — percentagem de proteínas (ex: 30 para 30%)
        carbs_pct    — percentagem de carboidratos (ex: 40 para 40%)
        fats_pct     — percentagem de gorduras (ex: 30 para 30%)
        weight_kg    — peso corporal em kg (usado para cálculo de g/kg)

    Devolve:
        MacroGrams com as quantidades em gramas e g/kg.

    Levanta:
        ValueError se as percentagens não somarem aproximadamente 100% ou se kcal_target for negativo.
    """
    total_pct = protein_pct + carbs_pct + fats_pct
    if not isclose(total_pct, 100.0, rel_tol=0.0, abs_tol=1.0):
        raise ValueError(f"As percentagens devem somar aproximadamente 100%. Soma atual: {total_pct:.2f}%")
    
    if kcal_target < 0:
        raise ValueError("Calorias deve ser um valor positivo.")
    
    if weight_kg <= 0:
        raise ValueError("Peso deve ser um valor positivo.")
    for name, value in {
        "protein_pct": protein_pct,
        "carbs_pct": carbs_pct,
        "fats_pct": fats_pct,
    }.items():
        if value < 0 or value > 100:
            raise ValueError(f"{name} deve ser entre 0 e 100. Valor atual: {value}")
    
    
    #Calcula calorias de cada macronutriente
    protein_kcal = (protein_pct / 100) * kcal_target
    carbs_kcal = (carbs_pct / 100) * kcal_target
    fats_kcal = (fats_pct / 100) * kcal_target

    #Converte calorias para gramas
    protein_g = round(protein_kcal / KCAL_PER_GRAM_PROTEIN,1)
    carbs_g = round(carbs_kcal / KCAL_PER_GRAM_CARBS,1)
    fats_g = round(fats_kcal / KCAL_PER_GRAM_FATS,1)

    #Calcula o total real de calorias baseado nos gramas arredondados
    kcal_real = round((protein_g * KCAL_PER_GRAM_PROTEIN) + 
                       (carbs_g * KCAL_PER_GRAM_CARBS) + 
                       (fats_g * KCAL_PER_GRAM_FATS),1)

    return MacroGrams(
        protein_g=protein_g,
        carbs_g=carbs_g,
        fats_g=fats_g,
        kcal_total=kcal_real,
        protein_g_per_kg=round(protein_g / weight_kg,2),
        carbs_g_per_kg=round(carbs_g / weight_kg,2),
        fats_g_per_kg=round(fats_g / weight_kg,2),
    )

def calculate_macros_from_grams_per_kg(
        weight_kg: float,
        protein_g_per_kg: float,
        carbs_g_per_kg: float,
        fats_g_per_kg: float,
) -> MacroGrams:
    """
    Calcula macros a partir de rácios g/kg de peso corporal.

    Não existe validação de soma — cada macro é independente.
    O PT define os rácios livremente e o kcal_from_macros resultante
    serve apenas como informação adicional.

    Fórmula: gramas = g_per_kg × peso_kg

    Exemplo (cliente 97kg):
        Proteína: 2.5 g/kg → 2.5 × 97 = 242.5g → 970 kcal
        Hidratos: 4.0 g/kg → 4.0 × 97 = 388.0g → 1552 kcal
        Gordura:  0.7 g/kg → 0.7 × 97 = 67.9g  → 611 kcal
        Total resultante: 3133 kcal

    Esta abordagem tem referências clínicas estabelecidas:
        Proteína: 1.6–2.2 g/kg para hipertrofia | 0.8–1.2 g/kg sedentário
        Gordura:  0.5–1.5 g/kg em geral
        Hidratos: 3.0–7.0 g/kg para desporto de resistência

    Levanta:
        ValueError se algum rácio for negativo.
    """
    if any(value < 0 for value in [protein_g_per_kg, carbs_g_per_kg, fats_g_per_kg]):
        raise ValueError("Rácios g/kg devem ser valores positivos.")
    
    #Gramas absolutas = rácio g/kg × peso
    protein_g = round(protein_g_per_kg * weight_kg,1)
    carbs_g = round(carbs_g_per_kg * weight_kg,1)
    fats_g = round(fats_g_per_kg * weight_kg,1)

    return _build_macro_grams(protein_g, carbs_g, fats_g, weight_kg)

#---------------------------------------------
#Helpers interno - constrói MacroGrams a partir de gramas absolutas
#---------------------------------------------

def _build_macro_grams(protein_g: float, carbs_g: float, fats_g: float, weight_kg: float) -> MacroGrams:
    """
    Calcula todas as métricas derivadas a partir das gramas base.
    Chamado internamente por ambos os métodos.

    Calcula:
      - kcal_from_macros : total calórico resultante dos macros definidos
      - g/kg             : para cada macro
      - percentagem kcal : para cada macro (informativo)
    """
    kcal_protein = protein_g * KCAL_PER_GRAM_PROTEIN
    kcal_carbs = carbs_g * KCAL_PER_GRAM_CARBS
    kcal_fats = fats_g * KCAL_PER_GRAM_FATS
    kcal_total = round(kcal_protein + kcal_carbs + kcal_fats,1)

    #Percentagens de kcal - protege contra divisão por zero
    if kcal_total > 0:
        protein_pct = round((kcal_protein / kcal_total) * 100,1)
        carbs_pct = round((kcal_carbs / kcal_total) * 100,1)
        fats_pct = round((kcal_fats / kcal_total) * 100,1)
    else:
        protein_pct = carbs_pct = fats_pct = 0.0
    
    return MacroGrams(
        protein_g=protein_g,
        carbs_g=carbs_g,
        fats_g=fats_g,
        kcal_total=kcal_total,
        protein_g_per_kg=round(protein_g / weight_kg,2) if weight_kg > 0 else 0.0,
        carbs_g_per_kg=round(carbs_g / weight_kg,2) if weight_kg > 0 else 0.0,
        fats_g_per_kg=round(fats_g / weight_kg,2) if weight_kg > 0 else 0.0,
        protein_pct=protein_pct,
        carbs_pct=carbs_pct,
        fats_pct=fats_pct,
    )

#---------------------------------------------
#Helpers: devolve os labels de atividade para o FE
#---------------------------------------------

def get_activity_factor_options() -> list[dict]:
    """
    Devolve a lista de fatores de atividade para popular um select no frontend.

    Exemplo de resposta:
    [
      {"key": "sedentary", "label": "Sedentário", "factor": 1.2, "description": "..."},
      ...
    ]
    """

    return [{
        "key": "sedentary",
        "label": "Sedentário (pouco ou nenhum exercício)",
        "factor": 1.2,
        "description": "Pouco ou nenhum exercício"
    }, {
        "key": "lightly_active",
        "label": "Pouco ativo (exercício leve 1-3x/semana)",
        "factor": 1.375,
        "description": "Exercício leve 1-3x/semana"
    }, {
        "key": "moderately_active",
        "label": "Moderadamente ativo (exercício moderado 3-5x/semana)",
        "factor": 1.55,
        "description": "Exercício moderado 3-5x/semana"
    }, {
        "key": "very_active",
        "label": "Muito ativo (exercício intenso 6-7x/semana)",
        "factor": 1.725,
        "description": "Exercício intenso 6-7x/semana"
    }, {
        "key": "extremely_active",
        "label": "Extremamente ativo (trabalho físico diário + treino bidiário)",
        "factor": 1.9,
        "description": "Trabalho físico diário + treino bidiário"
    }]