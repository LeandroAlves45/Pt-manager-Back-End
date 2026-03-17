"""
Modelo para tokens de autenticação ativos.

Cada usuário autenticado possui, no máximo, uma linha nesta tabela.
Ao fazer login, a linha anterior é excluída e substituída — somente o token mais recente
por usuário é válido em um determinado momento.

Por que armazenar tokens no banco de dados?

Os JWTs são sem estado por design — uma vez emitidos, são válidos até expirarem,
mesmo após a reinicialização do servidor ou alteração da senha. Armazenar o token aqui
nos oferece duas funcionalidades:

1. Logout imediato: excluir a linha invalida o token instantaneamente.

2. Conveniência do Swagger: copie o token do banco de dados e cole no
campo HTTPBearer sem precisar fazer login novamente.

A coluna token contém a string JWT completa, que corresponde exatamente a cada requisição.
"""

import uuid
from datetime import datetime
 
from sqlmodel import SQLModel, Field
from app.utils.time import utc_now

class ActiveToken(SQLModel, table=True):

    __tablename__ = "active_tokens"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    # Foreign_key de users
    user_id: str = Field(foreign_key="users.id", index=True)

    token: str = Field(index=True)  # O JWT completo, para validação direta

    created_at: datetime = Field(default_factory=utc_now)

    expires_at: datetime = Field()