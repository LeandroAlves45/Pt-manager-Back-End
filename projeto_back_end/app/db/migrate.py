from pathlib import Path
from sqlalchemy import text
from app.db.session import engine

# Statements that are no-ops inside engine.begin() managed transactions
_TX_CONTROL = {"begin", "commit", "rollback"}


def _split_sql_statements(sql: str) -> list[str]:
    """
    Split SQL into individual statements, handling:
    - Single-line comments (--)
    - Dollar-quoted blocks ($$...$$) used in DO/FUNCTION bodies
    - Transaction control statements (BEGIN/COMMIT) are excluded
      because engine.begin() already manages the transaction.
    """
    statements = []
    buff = []
    in_dollar_block = False

    for line in sql.splitlines():
        stripped = line.strip()

        # Skip comments and empty lines outside dollar blocks
        if not in_dollar_block and (not stripped or stripped.startswith("--")):
            continue

        buff.append(line)

        # Track $$ block boundaries
        if "$$" in stripped:
            dollar_count = stripped.count("$$")
            if dollar_count % 2 == 1:          # odd → toggle state
                in_dollar_block = not in_dollar_block

        if not in_dollar_block and stripped.endswith(";"):
            stmt = "\n".join(buff).strip()
            stmt = stmt[:-1].strip()           # remove trailing ';'
            # Skip transaction control — engine.begin() handles this
            if stmt and stmt.lower() not in _TX_CONTROL:
                statements.append(stmt)
            buff = []

    tail = "\n".join(buff).strip()
    if tail and tail.lower() not in _TX_CONTROL:
        statements.append(tail)

    return statements


def run_migrations() -> None:
    """
    Executa migrações SQL em ordem, com rastreamento via schema_migrations.
    - Cada migration corre na sua própria transação.
    - Migrations já aplicadas são ignoradas (idempotente por design).
    """
    migrations_dir = Path(__file__).parent / "migrations"
    if not migrations_dir.exists():
        return

    scripts = sorted(migrations_dir.glob("*.sql"))
    if not scripts:
        return

    # Garante que a tabela de rastreamento existe
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name       VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            )
        """))

    # Lê migrations já aplicadas
    with engine.connect() as conn:
        result = conn.execute(text("SELECT name FROM schema_migrations"))
        applied = {row[0] for row in result}

    for script_path in scripts:
        name = script_path.name
        if name in applied:
            continue

        sql = script_path.read_text(encoding="utf-8").strip()
        if not sql:
            continue

        with engine.begin() as conn:
            raw = conn.connection  # DB-API connection

            # SQLite: executescript
            if hasattr(raw, "executescript"):
                raw.executescript(sql)
            else:
                for stmt in _split_sql_statements(sql):
                    conn.execute(text(stmt))

            conn.execute(
                text("INSERT INTO schema_migrations (name) VALUES (:name)"),
                {"name": name},
            )