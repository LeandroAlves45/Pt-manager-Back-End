# =============================================================================
# TESTES — calculate_macros_from_grams_per_kg
# =============================================================================

import pytest
from app.services.macro_calculator import (
    calculate_tmb_all_formulas, 
    calculate_macros_from_percentages, 
    calculate_macros_from_grams_per_kg,
    get_activity_factor_options,
    ACTIVITY_FACTORS,
)
    
#=============================================================================
#Fixtures
#=============================================================================

@pytest.fixture
def male_athlete():
    """Dados típicos de um atleta masculino para testes."""

    return {
        "weight_kg": 97.0,
        "height_cm": 174.0,
        "age": 26,
        "sex": "male",
        "activity_key": "very_active",
    }

@pytest.fixture
def female_client():
    """Dados típicos de uma cliente feminina para testes."""

    return {
        "weight_kg": 65.0,
        "height_cm": 165.0,
        "age": 30,
        "sex": "female",
        "activity_key": "moderately_active",
    }

#=============================================================================
# Testes - calculate_tmb_all_formulas
#=============================================================================

class TestCalculateTMBAllFormulas:
    """
    Agrupa todos os testes relacionados à função calculate_tmb_all_formulas.
    """

    def test_devolve_tres_formulas(self, male_athlete):
        """
        Verifica que a função devolve sempre exatamente 3 resultados,
        um por fórmula (Harris-Benedict, Mifflin, Waldemar).
        """
        tmb_results = calculate_tmb_all_formulas(**male_athlete)
        assert len(tmb_results) == 3, "A função deve devolver exatamente 3 resultados, um por fórmula."

    def test_formulas_ordenadas_por_tdee_crescente(self, male_athlete):
        """
        Verifica que os resultados estão ordenados por TDEE crescente.
        O resultado com menor TDEE deve ser o primeiro da lista.
        """
        results = calculate_tmb_all_formulas(**male_athlete)

        #zip (results, results[1:]) para criar pares consecutivos e verificar a ordem (r0, r1), (r1, r2)
        #Verifica que cada elemento tem TDEE menor ou igual ao próximo
        for current, next_result in zip(results, results[1:]):
            assert current.tdee <= next_result.tdee, (
                f"{current.formula} ({current.tdee}) deveria ser <="
                f" {next_result.formula} ({next_result.tdee})"
            )

            