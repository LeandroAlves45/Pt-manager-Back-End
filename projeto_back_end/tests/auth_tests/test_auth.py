"""
Testes unitários para o sistema de autenticação.

Estes testes cobrem as funções puras (sem base de dados):
    - hash_password / verify_password
    - create_access_token / decode do token

Para testes de integração (com BD), usa pytest com uma BD em memória (SQLite).

Executar: pytest tests/test_auth.py -v
"""

import pytest
from datetime import timedelta
from jose import jwt

#------------------------------
# Testes de hashing de passwords
#------------------------------

class TestPasswordHashing:
    """
    Testa o sistema de hash de passwords usando bcrypt
    """

    def test_hash_password_returns_string(self):
        #O hash deve ser uma string não vazia
        from app.core.security import hash_password
        result = hash_password("mysecretpassword123")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_starts_with_bcrypt_prefix(self):
        #O hash gerado por bcrypt deve começar com $2b$ ou $2a$
        from app.core.security import hash_password
        result = hash_password("anotherpassword456")
        assert result.startswith("$2b$")

    def test_hash_is_not_plain_text(self):
        #Confirma que o hash é diferente da password original
        from app.core.security import hash_password
        password = "mysecretpassword123"
        result = hash_password(password)
        assert result != password

    def test_same_password_produces_different_hashes(self):
        #Cada hash deve ser único mesmo para a mesma password (devido ao salt)
        from app.core.security import hash_password
        hash1 = hash_password("mysecretpassword123")
        hash2 = hash_password("mysecretpassword123")
        assert hash1 != hash2 #salts diferentes devem produzir hashes diferentes

    def test_verify_password_correct(self):
        #verify_password deve retornar True para a password correta
        from app.core.security import hash_password, verify_password
        password = "my_secret_password_123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_wrong(self):
        #verify_password deve retornar False para a password errada
        from app.core.security import hash_password, verify_password
        password = hash_password("my_secret_password_123")
        assert verify_password("wrong_password", password) is False

    def test_verify_password_empty_string(self):
        #Password vazia deve retornar False quando comparada com hash de password não vazia
        from app.core.security import hash_password, verify_password
        hashed = hash_password("non_empty_password")
        assert verify_password("", hashed) is False

    def test_verify_password_case_sensitive(self):
        #A verificação de password deve ser sensível a maiúsculas/minúsculas
        from app.core.security import hash_password, verify_password
        hashed = hash_password("CaseSensitive123")
        assert verify_password("casesensitive123", hashed) is False
        assert verify_password("CASESENSITIVE123", hashed) is False
        assert verify_password("CaseSensitive123", hashed) is True

#------------------------------
# Testes de criação e verificação de tokens JWT
#------------------------------

class TestJWTToken:
    """
    Testa a criação e verificação de tokens JWT
    """

    def test_create_access_token_returns_string(self):
        #create_access_token deve retornar uma string não vazia
        from app.core.security import create_access_token
        token = create_access_token(subject="user123", role="trainer", full_name="Test User")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_correct_subject(self):
        # O payload do token deve conter user_id correto no campo "sub".
        from app.core.security import create_access_token, ALGORITHM
        from app.core.config import settings

        user_id = "test_user123"
        token = create_access_token(subject=user_id, role="trainer", full_name="Test User")

        #Decoda sem verificar expiração para isolar o teste
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert payload["sub"] == user_id

    def test_token_contains_correct_role(self):
        # O payload do token deve conter o role correto.
        from app.core.security import create_access_token, ALGORITHM
        from app.core.config import settings

        token = create_access_token(subject="user123", role="client", full_name="Test User")
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert payload["role"] == "client"

    def test_token_contains_client_id_when_provided(self):
        # Se client_id for fornecido, deve estar presente no payload do token
        from app.core.security import create_access_token, ALGORITHM
        from app.core.config import settings

        client_id = "client_456"
        token = create_access_token(subject="user123", role="client", full_name="Test User", client_id=client_id)
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert payload["cid"] == client_id

    def test_token_without_client_id_has_no_cid_claim(self):
        # Trainer tokens não devem conter o claim "cid"
        from app.core.security import create_access_token, ALGORITHM
        from app.core.config import settings

        token = create_access_token(subject="trainer-123", role="trainer", full_name="Test User")
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert "cid" not in payload

    def test_token_has_expiration(self):
        # O token deve conter uma data de expiração (claim "exp")
        from app.core.security import create_access_token, ALGORITHM
        from app.core.config import settings

        token = create_access_token(subject="user123", role="trainer", full_name="Test User")
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert "exp" in payload

    def test_custom_expiration_is_respected(self):
        # Se for fornecida uma expiração personalizada, deve ser refletida no token
        from app.core.security import create_access_token, ALGORITHM
        from app.core.config import settings
        from datetime import datetime, timezone

        custom_exp = timedelta(minutes=60)
        token = create_access_token(subject="user123", role="trainer", full_name="Test User", expires_delta=custom_exp)
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        
        # Verifica se a expiração é aproximadamente 60 minutos a partir do momento da criação
        now = datetime.now(timezone.utc).timestamp()
        # o token deve expirar entre 59 e 61 minutos a partir de agora
        assert payload["exp"] > now + (59 * 60) 
        assert payload["exp"] < now + (61 * 60)

    def test_trainer_and_client_tokens_differ(self):
        # Tokens para trainers e clients devem ser diferentes mesmo com o mesmo user_id
        from app.core.security import create_access_token

        trainer_token = create_access_token(subject="user123", role="trainer", full_name="Test User")
        client_token = create_access_token(subject="user123", role="client", full_name="Test User")

        assert trainer_token != client_token