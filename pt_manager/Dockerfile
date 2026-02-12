FROM python:3.11-slim

WORKDIR /app

#instala as dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

#copia requirements.txt e instala as dependências do Python
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY app ./app


#criar diretório de logs
RUN mkdir -p logs

#executa a aplicação
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0 --port 8000