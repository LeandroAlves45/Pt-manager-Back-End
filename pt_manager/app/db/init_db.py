from sqlmodel import SQLModel
from app.db.session import engine

#importar modelos garante que o SQLModel "vê" as tabelas
from app.db.models.client import Client #noqa: F401
from app.db.models.pack import PackType, ClientPack #noqa: F401

def init_db() -> None:
    """
    Cria as tabelas na BD caso não existam
    Em produto, isto é substituido por migrações
    """
    SQLModel.metadata.create_all(engine)