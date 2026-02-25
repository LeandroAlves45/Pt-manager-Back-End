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

    def test_tmb_e_tdee_sao_positivos(self, male_athlete):
        """
        Verifica que os valores de TMB e TDEE são positivos para um atleta típico.
        """
        results = calculate_tmb_all_formulas(**male_athlete)
        for result in results:
            assert result.tmb > 0, f"{result.formula}: TMB deve ser positivo, mas devolveu {result.tmb}"
            assert result.tdee > 0, f"{result.formula}: TDEE deve ser positivo, mas devolveu {result.tdee}"

    def test_tdee_maior_que_tmb(self, male_athlete):
        """
        Verifica que o TDEE é sempre maior do que o TMB, já que inclui o fator de atividade.
        """
        results = calculate_tmb_all_formulas(**male_athlete)
        for result in results:
            assert result.tdee > result.tmb, (
                f"{result.formula}: TDEE ({result.tdee}) deve ser maior do que o TMB ({result.tmb})"
            )
    
    def test_cada_formula_tem_chave_unica(self, male_athlete):
        """
        As 3 fórmulas devem ter chaves distintas - sem duplicados
        """
        results = calculate_tmb_all_formulas(**male_athlete)
        formulas = [result.formula for result in results]

        assert len(set(formulas)) == 3

    def test_valores_harris_benedict_homem(self):
        """
        Testa os valores EXATOS da fórmula Harris-Benedict para homem.

        Cálculo manual para verificar:
          TMB = 88.362 + (13.397 × 97) + (4.799 × 174) − (5.677 × 26)
              = 88.362 + 1299.509 + 835.026 − 147.602
              = 2075.295 kcal
          TDEE = 2075.295 × 1.725 = 3579.9 kcal

        pytest.approx() permite uma tolerância de ±0.1% para arredondamentos.
        Sem isto, 3579.88 != 3579.9 falharia por diferença de casas decimais.
        """
        result= calculate_tmb_all_formulas(
            weight_kg=97.0,
            height_cm=174.0,
            age=26,
            sex= "male",
            activity_key= "very_active",
        )

        hb = next(r for r in result if r.formula == "Harris-Benedict")

        assert hb.tmb == pytest.approx(2075.3, abs=1.0)
        assert hb.tdee == pytest.approx(3579.9, abs=2.0)

    def test_mulher_tem_tmb_diferente_de_homem(self,male_athlete, female_client):
        """
        Homem e mulher com os mesmos dados biométricos devem ter TMB diferentes.
        Verifica que o parâmetro 'sex' está a ser usado nas fórmulas.
        """
        male_result = calculate_tmb_all_formulas(**male_athlete)
        female_result = calculate_tmb_all_formulas(**female_client)

        #compara tmb da mesma fórmula (Harris-Benedict) entre homem e mulher para verificar que são diferentes
        hb_female = next(r for r in female_result if r.formula == "Harris-Benedict")
        hb_male = next(r for r in male_result if r.formula == "Harris-Benedict")

        assert hb_female.tmb != hb_male.tmb

    def test_activity_key_invalida_levanta_erro(self, male_athlete):
        """
        Verifica que uma activity_key inválida levanta um ValueError.
        """

        dados= {**male_athlete, "activity_key": "super_active_nao_existe"}  # "super_active_nao_existe" não é uma chave válida

        with pytest.raises(ValueError) as exc_info:
            calculate_tmb_all_formulas(**dados)
        
        #Verifica também que a mensagem de erro contém a informação sobre a chave inválida
        assert "activity_key inválida" in str(exc_info.value)

    @pytest.mark.parametrize("activity_key", list(ACTIVITY_FACTORS.keys()))
    def test_todos_os_niveis_de_atividade_funcionam(self, activity_key):
        """
        Parametrize: corre este mesmo teste para cada activity_key válida.
        Em vez de escrever 5 testes iguais, escreves 1 e o pytest itera.

        O decorador @pytest.mark.parametrize recebe:
          - o nome da variável
          - a lista de valores a testar
        """

        results = calculate_tmb_all_formulas(
            weight_kg=80.0, height_cm=180, age=30, sex="male", activity_key=activity_key
        )

        assert len(results) == 3, f"Falhou para activity_key='{activity_key}': deve devolver 3 resultados"

#=============================================================================
# Testes - calculate_macros_from_percentages
#=============================================================================

class TestMacrosFromPercentages:

    def test_gramas_calculadas_corretamente(self):
        """
        Verifica o cálculo com valores conhecidos.

        Cálculo manual:
          3300 kcal, 29% P / 52% H / 19% G
          Proteína: 3300 × 0.29 / 4 = 239.25g
          Hidratos: 3300 × 0.52 / 4 = 429.0g
          Gordura:  3300 × 0.19 / 9 = 69.67g
        """

        result = calculate_macros_from_percentages(
            kcal_target=3300,
            protein_pct=29.0,
            carbs_pct=52.0,
            fats_pct=19.0,
            weight_kg=97.0,  # peso necessário para calcular gramas/kg
        )

        assert result.protein_g == pytest.approx(239.25, abs=1)
        assert result.carbs_g == pytest.approx(429.0, abs=1)
        assert result.fats_g == pytest.approx(69.67, abs=1)

    def test_kcal_total_consistente_com_gramas(self):
        """
        O kcal_total devolvido deve ser consistente com as gramas calculadas.
        Fórmula inversa: (P × 4) + (H × 4) + (G × 9) ≈ kcal_target
        """

        result = calculate_macros_from_percentages(
            kcal_target=3300,
            protein_pct=30.0,
            carbs_pct=45.0,
            fats_pct=25.0,
            weight_kg=75.0,
        )

        kcal_calculado = (result.protein_g * 4) + (result.carbs_g * 4) + (result.fats_g * 9)

        assert kcal_calculado == pytest.approx(result.kcal_total, abs=5), (
            f"Kcal calculado a partir dos macros ({kcal_calculado}) deve ser "
            f"aproximadamente igual ao kcal_total devolvido ({result.kcal_total})"
        )

    def test_g_por_kg_calculado(self):
        """
        Verifica que o g/kg é calculado corretamente.
        g_por_kg = gramas / peso_kg
        """

        result = calculate_macros_from_percentages(
            kcal_target=2500,
            protein_pct=30.0,
            carbs_pct=50.0,
            fats_pct=20.0,
            weight_kg=100.0,
        )

        assert result.protein_g_per_kg == pytest.approx(result.protein_g / 100.0, abs=0.1)

    def test_percentagens_que_nao_somam_100_levanta_erro(self):
        """
        Verifica que percentagens que não somam 100% levantam um ValueError.
        """

        with pytest.raises(ValueError) as exc_info:
            calculate_macros_from_percentages(
                kcal_target=2500,
                protein_pct=30.0,
                carbs_pct=50.0,
                fats_pct=30.0,  # Soma = 110%, inválido
                weight_kg=80.0,
            )
        
        assert "As percentagens devem somar aproximadamente 100%" in str(exc_info.value)

    def test_tolerancia_arredondamento(self):
        """
        Verifica que pequenas diferenças de arredondamento não causam falhas.
        Por exemplo, 29.999% em vez de 30% deve ser aceito.
        """
        #nao deve levantar erro, mesmo que a soma seja 99.999% ou 100.001% devido a arredondamento
        result = calculate_macros_from_percentages(
            kcal_target=3000,
            protein_pct=29.999,
            carbs_pct=50.001,
            fats_pct=20.0,
            weight_kg=90.0,
        )

        assert result.protein_g > 0

    @pytest.mark.parametrize("kcal, p, h, g", [
        (2000.0, 30.0, 50.0, 20.0),
        (1500.0, 40.0, 35.0, 25.0),#dieta com mais proteina
        (4000.0, 25.0, 55.0, 20.0),#dieta com mais hidratos
        (3500.0, 35.0, 40.0, 25.0),#dieta mais equilibrada
    ])    

    def test_varios_cenarios_retornam_valores_positivos(self, kcal, p, h, g):
        """
        Testa vários cenários de TDEE e percentagens para garantir que a função
        retorna valores positivos e faz os cálculos sem erros.
        """
        result = calculate_macros_from_percentages(
            kcal_target=kcal,
            protein_pct=p,
            carbs_pct=h,
            fats_pct=g,
            weight_kg=80.0,
        )

        assert result.protein_g > 0, f"Proteína deve ser positiva para TDEE={kcal}, P={p}%"
        assert result.carbs_g > 0, f"Hidratos devem ser positivos para TDEE={kcal}, H={h}%"
        assert result.fats_g > 0, f"Gordura deve ser positiva para TDEE={kcal}, G={g}%"



#=============================================================================
# Testes - calculate_macros_from_grams_per_kg
#=============================================================================

class TestMacrosFromGramsPerKg:

    def test_gramas_calculados_corretamente(self):
        """
        Verifica o cálculo com valores conhecidos.

        Cliente 97kg com rácios:
          Proteína: 2.5 g/kg → 2.5 × 97 = 242.5g
          Hidratos: 4.0 g/kg → 4.0 × 97 = 388.0g
          Gordura:  0.7 g/kg → 0.7 × 97 = 67.9g
        """

        result = calculate_macros_from_grams_per_kg(
            weight_kg=97.0,
            protein_g_per_kg=2.5,
            carbs_g_per_kg=4.0,
            fats_g_per_kg=0.7,
        )

        assert result.protein_g == pytest.approx(242.5, abs=1)
        assert result.carbs_g == pytest.approx(388.0, abs=1)
        assert result.fats_g == pytest.approx(67.9, abs=1)

    def test_kcal_total_calculado_a_partir_de_gramas(self):
        """
        Verifica que o kcal_total devolvido é consistente com as gramas calculadas.
        Fórmula: (P × 4) + (H × 4) + (G × 9) ≈ kcal_total
        """

        result = calculate_macros_from_grams_per_kg(
            weight_kg=97.0,
            protein_g_per_kg=2.5,  # 242.5g
            carbs_g_per_kg=4.0,    # 388g
            fats_g_per_kg=0.7,     # 67.9g
        )

        assert result.kcal_total == pytest.approx(3133.0, abs=10)

    def test_g_por_kg_igual_ao_input(self):
        """
        Verifica que o g/kg devolvido é igual ao input fornecido.
        """
        result = calculate_macros_from_grams_per_kg(
            weight_kg=80.0,
            protein_g_per_kg=2.0,
            carbs_g_per_kg=3.0,
            fats_g_per_kg=0.5,
        )

        assert result.protein_g_per_kg == pytest.approx(2.0, abs=0.05)
        assert result.carbs_g_per_kg == pytest.approx(3.0, abs=0.05)
        assert result.fats_g_per_kg == pytest.approx(0.5, abs=0.05)

    def test_racio_negativo_levanta_erro(self):
        """
        Verifica que um rácio negativo levanta um ValueError.
        """

        with pytest.raises(ValueError) as exc_info:
            calculate_macros_from_grams_per_kg(
                weight_kg=80.0,
                protein_g_per_kg=-1.0,  # Rácio negativo inválido
                carbs_g_per_kg=3.0,
                fats_g_per_kg=0.5,
            )
        
        assert "Rácios g/kg devem ser valores positivos." in str(exc_info.value)
    
    def test_percentagem_somam_100(self):
        """
        Independente do método, as % de kcal do resultado devem somar ~100%.
        """

        result = calculate_macros_from_grams_per_kg(
            weight_kg=90.0,
            protein_g_per_kg=2.0,  # 180g
            carbs_g_per_kg=3.0,    # 270g
            fats_g_per_kg=0.5,     # 45g
        )

        total_pct = result.protein_pct + result.carbs_pct + result.fats_pct

        assert total_pct == pytest.approx(100.0, abs=1)

#=============================================================================
# testes - get_activity_factor_options
#=============================================================================

class TestGetActivityFactorOptions:

    def test_devolve_cinco_opcoes(self):
        """
        Verifica que a função devolve exatamente 5 opções de fatores de atividade.
        """
        options = get_activity_factor_options()
        assert len(options) == 5, f"Deve devolver 5 opções, e devolveu {len(options)}"

    def test_cada_opcao_tem_campos_obrigatorios(self):
        """
        Verifica que cada opção devolvida tem os campos 'key', 'label' e 'factor'.
        """
        options = get_activity_factor_options()
        required_fields = {"key", "label", "factor"}

        for option in options:
            missing = required_fields - set(option.keys())
            assert not missing, f"Opção '{option.get('key')}' está faltando campos: {missing}"

    def test_chaves_correspondem_aos_fatores(self):
        """
        As chaves devolvidas devem corresponder exatamente ao dicionário
        ACTIVITY_FACTORS — sem extras, sem em falta.
        """

        options = get_activity_factor_options()
        option_keys = {option["key"] for option in options}

        assert option_keys == set(ACTIVITY_FACTORS.keys()), (
            f"As chaves das opções {option_keys} devem corresponder às chaves de ACTIVITY_FACTORS {set(ACTIVITY_FACTORS.keys())}"
        )

    def test_fatores_correspondem_ao_dicionario(self):
        """
        Verifica que os fatores devolvidos em cada opção correspondem aos valores do dicionário ACTIVITY_FACTORS.
        """

        options = get_activity_factor_options()
        for option in options:
            expected_factor = ACTIVITY_FACTORS[option["key"]]
            assert option["factor"] == pytest.approx(expected_factor)