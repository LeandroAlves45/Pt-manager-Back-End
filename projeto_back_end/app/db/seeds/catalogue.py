"""
Seed do catálogo global — exercícios, alimentos e suplementos pré-definidos.
 
Executado no startup da aplicação, após as migrations e os outros seeds.
É idempotente: verifica por nome antes de inserir — seguro de re-executar
em cada reinício do container sem criar duplicados.
 
Catálogos globais (owner_trainer_id / created_by_user_id = NULL):
    - Visíveis a todos os trainers
    - Não podem ser editados por trainers (apenas pelo superuser via admin)
    - Trainers podem criar os seus próprios exercícios/alimentos/suplementos
      adicionais, que ficam privados (com o seu ID)
"""

import logging
from sqlmodel import Session, select

from app.db.models.training import Exercise
from app.db.models.nutrition import Food
from app.db.models.supplement import Supplement

logger = logging.getLogger(__name__)

# =============================================================================
# EXERCÍCIOS 
# =============================================================================

GLOBAL_EXERCISES = [
    # --------------------------- PEITO ---------------------------
    {"name": "Supino Reto com Barra Livre", "muscles": "Peito, Tríceps, Ombros", "url": "https://youtube.com/shorts/UHa9U-O09_U?si=TCAWERCz-6gbnqCM"},
    {"name": "Supino Reto com Halteres", "muscles": "Peito, Tríceps, Ombros", "url": "https://youtube.com/shorts/hlV6f0kHmeo?si=5kFu9Y0ILcmGoNnF"},
    {"name": "Supino Inclinado com Barra Livre", "muscles": "Peito, Tríceps, Ombros", "url": "https://youtube.com/shorts/QMR4_KzcTqs?si=wKcr3rF4Z4BwGTln"},
    {"name": "Supino Inclinado com Halteres", "muscles": "Peito, Tríceps, Ombros", "url": "https://youtube.com/shorts/ZaNyRjpoki8?si=0LA4k2X99fcbxDuO"},
    {"name": "Peck Deck", "muscles": "Peito", "url": "https://youtu.be/MENdoLpyj7c?si=QNFLpaFvmOlKhiBw"},
    {"name": "Crossover Médio", "muscles": "Peito", "url": "https://youtube.com/shorts/u9XJPXz8EVU?si=3ZaNfTMLIx5N8Mni"},
    {"name": "Crossover Baixo", "muscles": "Peito", "url": "https://youtu.be/Od9914tc8sg?si=Ok28v1yN5iYZyt2l"},
    {"name": "Crossover Alto", "muscles": "Peito", "url": "https://youtu.be/55nyV_aosNk?si=HGklF3DxR7W0_mHX"},

    # --------------------------- COSTAS ---------------------------
    {"name": "Puxada Pega Aberta", "muscles": "Costas, Bíceps", "url": "https://youtu.be/_2MfZAj98tk?si=mVsDIHVOvPN-CUw3"},
    {"name": "Remada Curvada com Barra Livre Pega Pronada", "muscles": "Costas, Bíceps", "url": "https://youtube.com/shorts/e53vSzibkO0?si=pD04fI1NvTCy9FZO"},
    {"name": "Remada Curvada no banco 45º", "muscles": "Costas, Bíceps", "url": "https://youtu.be/Uj-EZXWbQHU?si=28SP6Pr0Bbjrvhcm"},
    {"name": "Remada Unilateral com Halteres", "muscles": "Costas, Bíceps", "url": "https://youtu.be/L2FuijYFTvE?si=r6F9MW1btk2eogNA"},
    {"name": "Remada Comboio", "muscles": "Costas, Bíceps", "url": "https://youtu.be/7lc8Ow4vIwA?si=z-1-hSuaJ8atHSLc"},
    {"name": "Puxada com Pegada Triângulo", "muscles": "Costas, Bíceps", "url": "https://youtu.be/dY_dfz-d1ko?si=yWHV8PtAHS3HnX1s"},

    # --------------------------- PERNAS ---------------------------
    {"name": "Agachamento Livre", "muscles": "Quadríceps, Glúteos", "url": "https://youtu.be/vwV4izNPOh4?si=NVK3ilI5rxPVQHPG"},
    {"name": "Agachamento Frontal com Barra Livre", "muscles": "Quadríceps", "url": "https://youtu.be/gWWWOH59P8s?si=C672dYUkEZCr6Gqp"},
    {"name": "Bulgarian Split com Halteres", "muscles": "Quadríceps", "url": "https://www.youtube.com/watch?v=Fmjj7wFJWRE&pp=ygUWYnVsZ2FyaWFuIHNxdWF0IGhhbHRlcg%3D%3D"},
    {"name": "Leg Press 45º", "muscles": "Quadríceps", "url": "https://youtube.com/shorts/NY5fw4Zaofg?si=jIUlvbAzjhAi8bxB"},
    {"name": "Cadeira Extensora", "muscles": "Quadríceps", "url": "https://youtu.be/PzIfB9MiiX8?si=8BuFkRAJFNmJmarh"},
    {"name": "Cadeira Flexora", "muscles": "Femoral", "url": "https://youtu.be/T46yKiz8laY?si=BwBVjifWLoZhszeo"},

    # --------------------------- OMBROS ---------------------------
    {"name": "Press Ombro com Barra Livre", "muscles": "Ombros", "url": "https://youtu.be/930c6LGuO6Q?si=nhss6TT2i_551v4C"},
    {"name": "Press Ombro com Halteres", "muscles": "Ombros", "url": "https://youtu.be/5I7ogOjvdnc?si=-nZs4KD57yWoNFz3"},
    {"name": "Elevação Lateral com Halteres", "muscles": "Ombros", "url": "https://youtu.be/ot9nwSC1JnA?si=GMVmcr27IEFB5g41"},
    {"name": "Elevação Frontal com Halteres", "muscles": "Ombros", "url": "https://youtu.be/GqZRmCow0rw?si=4K1W4eNDRO9o6Buk"},
    {"name": "Peck Deck Invertido", "muscles": "Ombros", "url": "https://youtu.be/wUT3hmnzq3c?si=8FTPL32VG5uI_krj"},
    {"name": "Encolhimento de Ombros com Halteres", "muscles": "Trapézio", "url": "https://youtube.com/shorts/x9Im5d1H-Xw?si=S9r03h-NqbCdNBdn"},

    # --------------------------- BÍCEPS ---------------------------
    {"name": "Bícep Curl com Halteres", "muscles": "Bíceps", "url": "https://youtu.be/xXp3mV3OOZo?si=8B34TeFZM6OOnpoS"},
    {"name": "Bícep Curl com Halteres no Banco Inclinado", "muscles": "Bíceps", "url": "https://youtu.be/N1niow42B5I?si=IhRzywi6lOB6U3ek"},
    {"name": "Bícep Martelo", "muscles": "Bíceps", "url": "https://youtu.be/0rRpv6o140o?si=1eYSEYz61YsAVTlU"},
    {"name": "Bícep Scott com Barra W", "muscles": "Bíceps", "url": "https://youtube.com/shorts/fjS0CqDR4v8?si=K8vUGivmWkyjrIUb"},
    {"name": "Bícep Concentrado com Halteres", "muscles": "Bíceps", "url": "https://youtu.be/c0vYYI_mbXU?si=PKwiDv-1XBlfqqzO"},

    # --------------------------- TRÍCEPS ---------------------------
    {"name": "Tríceps Testa com Barra W", "muscles": "Tríceps", "url": "https://youtu.be/40Cx-IfJhA0?si=LSFokZ-_G7ZhPgNZ"},
    {"name": "Tríceps Corda", "muscles": "Tríceps", "url": "https://youtu.be/-QGC1cL6ETE?si=kmmQJpQ72PG2x4XX"},
    {"name": "Dips/Afundos", "muscles": "Tríceps", "url": "https://youtu.be/x3sgFGDyTiQ?si=G3b_nW0H-mhyOViS"},
    {"name": "Tríceps Francês com Halteres", "muscles": "Tríceps", "url": "https://youtu.be/_dtPoiFWZT4?si=cx9dWH6fHnrtdGZT"},
    {"name": "Tríceps Francês com corda", "muscles": "Tríceps", "url": "https://youtu.be/dMYGgTbtRIQ?si=qoxVWV7R78vO5dGT"},
]

# =============================================================================
# ALIMENTOS — 
# =============================================================================

GLOBAL_FOODS = [
    # ── Proteínas Animais ────────────────────────────────────────────────────
    {"name": "Frango (Peito, cozido)",      "carbs": 0.0,  "protein": 31.0, "fats": 3.6},
    {"name": "Bife de Vaca (magro, grelhado)", "carbs": 0.0, "protein": 26.0, "fats": 7.0},
    {"name": "Salmão (grelhado)",           "carbs": 0.0,  "protein": 25.0, "fats": 13.0},
    {"name": "Atum (em água, escorrido)",   "carbs": 0.0,  "protein": 26.0, "fats": 0.9},
    {"name": "Ovos Inteiros",               "carbs": 1.1,  "protein": 13.0, "fats": 11.0},
    {"name": "Claras de Ovo",               "carbs": 0.7,  "protein": 11.0, "fats": 0.2},
    {"name": "Bacalhau (cozido, demolhado)", "carbs": 0.0, "protein": 20.0, "fats": 1.0},
    {"name": "Peru (peito, cozido)",        "carbs": 0.0,  "protein": 29.0, "fats": 3.0},
 
    # ── Lacticínios ──────────────────────────────────────────────────────────
    {"name": "Queijo Cottage",              "carbs": 3.4,  "protein": 11.0, "fats": 4.3},
    {"name": "Iogurte Grego (natural, 0%)", "carbs": 3.6,  "protein": 10.0, "fats": 0.4},
    {"name": "Leite Meio-Gordo",            "carbs": 4.8,  "protein": 3.4,  "fats": 1.6},
    {"name": "Queijo Mozzarella (light)",   "carbs": 2.2,  "protein": 24.0, "fats": 16.0},
    {"name": "Requeijão",                   "carbs": 3.0,  "protein": 9.0,  "fats": 6.0},
 
    # ── Hidratos de Carbono ──────────────────────────────────────────────────
    {"name": "Arroz Branco (cozido)",       "carbs": 28.0, "protein": 2.7,  "fats": 0.3},
    {"name": "Arroz Integral (cozido)",     "carbs": 23.0, "protein": 2.6,  "fats": 0.9},
    {"name": "Massa de Trigo (cozida)",     "carbs": 25.0, "protein": 5.0,  "fats": 0.9},
    {"name": "Batata (cozida, sem pele)",   "carbs": 17.0, "protein": 2.0,  "fats": 0.1},
    {"name": "Batata-Doce (cozida)",        "carbs": 20.0, "protein": 1.6,  "fats": 0.1},
    {"name": "Aveia (flocos)",              "carbs": 66.0, "protein": 13.0, "fats": 7.0},
    {"name": "Pão de Mistura",              "carbs": 48.0, "protein": 8.0,  "fats": 2.0},
 
    # ── Leguminosas ──────────────────────────────────────────────────────────
    {"name": "Feijão Vermelho (cozido)",    "carbs": 22.0, "protein": 8.7,  "fats": 0.5},
    {"name": "Grão-de-Bico (cozido)",       "carbs": 27.0, "protein": 9.0,  "fats": 2.6},
    {"name": "Lentilhas (cozidas)",         "carbs": 20.0, "protein": 9.0,  "fats": 0.4},
 
    # ── Gorduras Saudáveis ───────────────────────────────────────────────────
    {"name": "Abacate",                     "carbs": 9.0,  "protein": 2.0,  "fats": 15.0},
    {"name": "Azeite Extra Virgem",         "carbs": 0.0,  "protein": 0.0,  "fats": 100.0},
    {"name": "Amêndoas",                    "carbs": 22.0, "protein": 21.0, "fats": 50.0},
    {"name": "Nozes",                       "carbs": 14.0, "protein": 15.0, "fats": 65.0},
 
    # ── Fruta ────────────────────────────────────────────────────────────────
    {"name": "Banana",                      "carbs": 23.0, "protein": 1.1,  "fats": 0.3},
    {"name": "Maçã",                        "carbs": 14.0, "protein": 0.3,  "fats": 0.2},
    {"name": "Laranja",                     "carbs": 12.0, "protein": 0.9,  "fats": 0.1},
    {"name": "Morango",                     "carbs": 8.0,  "protein": 0.7,  "fats": 0.3},
 
    # ── Vegetais ─────────────────────────────────────────────────────────────
    {"name": "Brócolos (cozidos)",          "carbs": 7.0,  "protein": 2.8,  "fats": 0.4},
    {"name": "Espinafres (crus)",           "carbs": 3.6,  "protein": 2.9,  "fats": 0.4},
    {"name": "Cenoura (crua)",              "carbs": 10.0, "protein": 0.9,  "fats": 0.2},
    {"name": "Tomate",                      "carbs": 3.9,  "protein": 0.9,  "fats": 0.2},
]
 
 
# =============================================================================
# SUPLEMENTOS — 10 suplementos mais usados em fitness
# =============================================================================
 
GLOBAL_SUPPLEMENTS = [
    {
        "name": "Proteína Whey (Concentrado)",
        "description": "Proteína de soro de leite de rápida absorção. Ideal para recuperação pós-treino.",
        "serving_size": "30g (1 scoop)",
        "timing": "Pós-treino",
    },
    {
        "name": "Creatina Monohidratada",
        "description": "Aumenta a força, potência e recuperação muscular. Um dos suplementos mais estudados e eficazes.",
        "serving_size": "5g",
        "timing": "Qualquer hora (consistência é o mais importante)",
    },
    {
        "name": "BCAA (Aminoácidos de Cadeia Ramificada)",
        "description": "Leucina, Isoleucina e Valina. Ajuda a prevenir o catabolismo muscular durante treinos em jejum.",
        "serving_size": "10g",
        "timing": "Durante o treino ou em jejum",
    },
    {
        "name": "Cafeína",
        "description": "Aumenta o foco, energia e performance. Tomar com moderação e evitar após as 15h.",
        "serving_size": "200mg (1 cápsula)",
        "timing": "30-45 min antes do treino",
    },
    {
        "name": "Beta-Alanina",
        "description": "Reduz a fadiga muscular em exercícios de alta intensidade. Pode causar formigueiro (parestesia) — normal e inofensivo.",
        "serving_size": "3.2g",
        "timing": "Pré-treino",
    },
    {
        "name": "Vitamina D3",
        "description": "Essencial para a saúde óssea, função imune e síntese de testosterona. Défice comum em climas com pouca exposição solar.",
        "serving_size": "2000-4000 UI (1 cápsula)",
        "timing": "Com a refeição principal (com gordura)",
    },
    {
        "name": "Ómega-3 (EPA/DHA)",
        "description": "Ácidos gordos essenciais com efeito anti-inflamatório. Apoia a recuperação muscular e saúde cardiovascular.",
        "serving_size": "2 cápsulas (1g EPA+DHA)",
        "timing": "Com as refeições",
    },
    {
        "name": "Magnésio",
        "description": "Essencial para mais de 300 reações enzimáticas. Melhora a qualidade do sono e reduz cãibras.",
        "serving_size": "300-400mg",
        "timing": "Antes de dormir",
    },
    {
        "name": "ZMA (Zinco, Magnésio, Vitamina B6)",
        "description": "Combinação que suporta a recuperação noturna, qualidade do sono e produção hormonal.",
        "serving_size": "3 cápsulas",
        "timing": "30 min antes de dormir, com o estômago vazio",
    },
    {
        "name": "Glutamina",
        "description": "Aminoácido não essencial que suporta a recuperação e o sistema imunitário em períodos de treino intenso.",
        "serving_size": "5g",
        "timing": "Pós-treino ou antes de dormir",
    },
]

# =============================================================================
# FUNÇÃO SEED — idempotente
# =============================================================================

def seed_catalogue(session: Session) -> None:
    """
    Seed idempotente do catálogo global.
 
    Verifica por nome antes de inserir — não cria duplicados mesmo que
    a função seja chamada múltiplas vezes (em cada reinício do container).
 
    Critério de "global":
        Exercise  → owner_trainer_id = None
        Food      → owner_trainer_id = None
        Supplement → created_by_user_id = None
    """
    _seed_exercises(session)
    _seed_foods(session)
    _seed_supplements(session)
    session.commit()  # Commit após todas as inserções
    logger.info("[SEED] Catálogo global concluído com sucesso.")

def _seed_exercises(session: Session) -> None:
    """ Insere exercícios globais se não existirem (owner_trainer_id = None). """
    # Busca apenas exercicios globais existentes para verificar duplicados

    existing_names = {
        e.name for e in session.exec(
            select(Exercise).where(Exercise.owner_trainer_id.is_(None))
        ).all()
    }

    inserted = 0
    for data in GLOBAL_EXERCISES:
        if data["name"] not in existing_names:
            session.add(Exercise(
                name=data["name"],
                muscles=data["muscles"],
                url=data["url"],
                is_active=True,
                owner_trainer_id=None,  # Marca como global
            ))
            inserted += 1
    
    if inserted:
        logger.info(f"[SEED] Exercícios: {inserted} inseridos ({len(GLOBAL_EXERCISES)} no catálogo).")
    else:
        logger.info(f"[SEED] Exercícios: catálogo já actualizado ({len(GLOBAL_EXERCISES)} registos).")

def _seed_foods(session: Session) -> None:
    """ Insere alimentos globais se não existirem (owner_trainer_id = None). """
    existing_names = {
        f.name for f in session.exec(
            select(Food).where(Food.owner_trainer_id.is_(None))
        ).all()
    }

    inserted = 0
    for data in GLOBAL_FOODS:
        if data["name"] not in existing_names:
            session.add(Food(
                name=data["name"],
                carbs=data["carbs"],
                protein=data["protein"],
                fats=data["fats"],
                is_active=True,
                owner_trainer_id=None,  # Marca como global
            ))
            inserted += 1
    
    if inserted:
        logger.info(f"[SEED] Alimentos: {inserted} inseridos ({len(GLOBAL_FOODS)} no catálogo).")
    else:
        logger.info(f"[SEED] Alimentos: catálogo já actualizado ({len(GLOBAL_FOODS)} registos).")

def _seed_supplements(session: Session) -> None:
    """ Insere suplementos globais se não existirem (created_by_user_id = None). """
    existing_names = {
        s.name for s in session.exec(
            select(Supplement).where(Supplement.created_by_user_id.is_(None))
        ).all()
    }

    inserted = 0
    for data in GLOBAL_SUPPLEMENTS:
        if data["name"] not in existing_names:
            session.add(Supplement(
                name=data["name"],
                description=data["description"],
                serving_size=data["serving_size"],
                timing=data["timing"],
                created_by_user_id=None,  # Marca como global
            ))
            inserted += 1
    
    if inserted:
        logger.info(f"[SEED] Suplementos: {inserted} inseridos ({len(GLOBAL_SUPPLEMENTS)} no catálogo).")
    else:
        logger.info(f"[SEED] Suplementos: catálogo já actualizado ({len(GLOBAL_SUPPLEMENTS)} registos).")