# Imagem base com Python 3.11
FROM python:3.11-slim

# Define o diretório de trabalho
WORKDIR /app

# Copia e instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY app ./app

# Evita buffering de output do Python (logs aparecem imediatamente)
ENV PYTHONUNBUFFERED=1

# Inicia a aplicação
# ${PORT:-8000} usa a variável PORT do Railway, ou 8000 como fallback
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}