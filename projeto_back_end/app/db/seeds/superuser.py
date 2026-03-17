"""
Seed do superuser — garante que existe sempre uma conta de superuser na base de dados.
 
Executado no startup da aplicação (on_startup em main.py), após as migrações.
É idempotente: verifica se o email já existe antes de criar — seguro de re-executar
em cada reinício do container sem criar duplicados.
 
Credenciais lidas de variáveis de ambiente:
    SUPERUSER_EMAIL     — email de login
    SUPERUSER_PASSWORD  — password em texto plano (convertida para hash aqui)
    SUPERUSER_NAME      — nome completo (opcional, default: "Admin")
 
Se as variáveis não estiverem definidas, a seed é ignorada silenciosamente.
Isto permite correr o backend localmente sem definir essas variáveis.
"""

import logging
from sqlmodel import Session, select
from app.db.models.user import User
from app.core.security import hash_password
from app.core.config import settings

logger = logging.getLogger(__name__)

def seed_superuser(session: Session) -> None:
    """
    Cria o utilizador superuser se ainda não existir.

    Chamado em on_startup() no main.py, depois de run_migrations().
    Usa o email como identificador único — se já existir um utilizador
    com esse email, não faz nada (mesmo que o role seja diferente).
    """

    # Lê as credenciais do settings (pydantic-settings lê o .env correctamente)
    email = settings.superuser_email
    password = settings.superuser_password
    name = settings.superuser_name

    # Se as variáveis não estiverem definidas , ignora a seed
    if not email or not password:
        logger.info("SUPERUSER_EMAIL ou SUPERUSER_PASSWORD não definidos. Ignorando seed do superuser.")
        return
    
    # Verifica se já existe um utilizador com esse email
    existing_user = session.exec(select(User).where(User.email == email)).first()

    if existing_user:
        logger.info(f"[SEED] Superuser com email '{email}' já existe. Ignorando criação.")
        return
    
    # Cria o superuser com:
    # -- is_exempt_from_billing = True (não paga subscrição)
    # -- role = "superuser" (acesso total)
    # -- is_active = True (conta ativa)
    superuser = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=name,
        role="superuser",
        is_active=True,
        is_exempt_from_billing=True,
    )

    session.add(superuser)

    try:
        session.commit()
        logger.info(f"[SEED] Superuser criado com email '{email}'.")
    except Exception as e:
        session.rollback()
        logger.error(f"Erro ao criar superuser: {e}")
