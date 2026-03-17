from pathlib import Path
from sqlalchemy import text
from app.db.session import engine

def _split_sql_statements(sql: str) -> list[str]:
    """
    Split simples por ';' para migrações manuais.

    Nota:
    - Isto é suficiente para os teus scripts atuais (CREATE INDEX, etc.)
    - Evita usar para functions complexas com $$...$$ sem ajustar.
    """
    statements = []
    buff = []

    for line in sql.splitlines():
        stripped = line.strip()

        # ignora comentários e linhas vazias
        if not stripped or stripped.startswith("--"):
            continue

        buff.append(line)

        if stripped.endswith(";"):
            stmt = "\n".join(buff).strip()
            stmt = stmt[:-1].strip()  # remove ';' final
            if stmt:
                statements.append(stmt)
            buff = []

    # resto
    tail = "\n".join(buff).strip()
    if tail:
        statements.append(tail)

    return statements


def run_migrations() -> None:
    """
    Migrações simples via SQL (manual)
    - Executa scripts em ordem
    - Sem controlo schema_migrations (MVP)
    """
    migrations_dir = Path(__file__).parent / "migrations"
    if not migrations_dir.exists():
        return

    scripts = sorted(migrations_dir.glob("*.sql"))
    if not scripts:
        return

    with engine.begin() as conn:
        raw = conn.connection  # DB-API connection

        for script_path in scripts:
            sql = script_path.read_text(encoding="utf-8").strip()
            if not sql:
                continue

            # SQLite: executescript
            if hasattr(raw, "executescript"):
                raw.executescript(sql)
                continue

            # Postgres (ou outros): executa statement a statement
            for stmt in _split_sql_statements(sql):
                conn.execute(text(stmt))