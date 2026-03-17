from sqlmodel import Session, select
from app.db.models.pack import PackType  

def seed_pack_types(session: Session) -> None:
    """
    Seed idempotente:
    - Garante PackTypes 2/4/6/8 aulas
    - Atualiza nome/is_active se já existirem
    """
    desired = [2, 4, 6, 8]

    existing = session.exec(select(PackType)).all()
    by_sessions = {pt.sessions_total: pt for pt in existing}

    for n in desired:
        name = f"Pack {n} aulas"

        if n in by_sessions:
            pt = by_sessions[n]
            pt.name = name
            pt.is_active = True
            session.add(pt)
        else:
            session.add(PackType(name=name, sessions_total=n, is_active=True))

    # Opcional: desativar outros tipos
    for pt in existing:
        if pt.sessions_total not in desired:
            pt.is_active = False
            session.add(pt)

    session.commit()
