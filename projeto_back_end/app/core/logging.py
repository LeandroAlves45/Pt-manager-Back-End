"""
logging.py — configuração centralizada de logging estruturado.
 
Formato: timestamp | nível | módulo | mensagem
Destinos: console (INFO+) e ficheiro rotativo (DEBUG+)
 
Convenções de logging no PT Manager:
  logger.info(...)    — operações normais (criação de plano, login, etc.)
  logger.warning(...) — situações inesperadas não fatais (plano sem alimentos, etc.)
  logger.error(...)   — erros recuperáveis (BD, API externa, validação)
  logger.exception(.) — erros não esperados — inclui stack trace automático
 
Uso em qualquer módulo:
  import logging
  logger = logging.getLogger(__name__)
  logger.error("[NUTRITION] Erro ao criar plano para cliente %s: %s", client_id, str(e))
 
Prefixos recomendados por domínio (facilita grep nos logs do Render):
  [AUTH]       — autenticação, tokens, sessões
  [NUTRITION]  — planos alimentares, calculadora de macros
  [BILLING]    — Stripe, subscrições, webhooks
  [SESSIONS]   — sessões de treino, packs
  [SENTRY]     — inicialização do Sentry
  [STARTUP]    — arranque da app, migrations, seeds
  [DB]         — erros de base de dados (IntegrityError, SQLAlchemyError)
"""

import logging
import sys
import os
from logging.handlers import RotatingFileHandler

def setup_logging():
    """
    Configura logging estruturado para a aplicação.
 
    Console: INFO e acima (visível nos logs do Render)
    Ficheiro: DEBUG e acima — rotativo 10MB, 5 backups
              (apenas em desenvolvimento — Render não tem disco persistente)
    """

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(log_format, date_format)
 
    # Handler de console — sempre ativo (Render captura stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
 
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
 
    # Handler de ficheiro — apenas se o diretório logs/ existir
    # Em produção (Render) não há disco persistente, por isso é opcional.
    # Em desenvolvimento, cria o diretório automaticamente.
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir, exist_ok=True)
        except OSError:
            # Sem permissão para criar o diretório — apenas console
            pass
 
    if os.path.exists(logs_dir):
        file_handler = RotatingFileHandler(
            os.path.join(logs_dir, "app.log"),
            maxBytes=10 * 1024 * 1024,  # 10MB por ficheiro
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
 
    # Silenciar bibliotecas externas — demasiado verbosas
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("stripe").setLevel(logging.WARNING)