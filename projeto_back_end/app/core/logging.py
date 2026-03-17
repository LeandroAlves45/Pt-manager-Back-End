import logging
import sys
from logging.handlers import RotatingFileHandler

def setup_logging():
    """
    Configura logging estruturado para a aplicação.
    
    - Console: INFO e acima
    - Arquivo: DEBUG e acima (rotativo 10MB, 5 backups)    
    """

    #formato detalhado com timestamp, nível e mensagem
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    #handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))

    #handler para arquivo rotativo
    file_handler = RotatingFileHandler("logs/app.log", maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))

    #configurar logger raiz
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # captura tudo, handlers filtram
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    #silenciar logs de bibliotecas externas
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)