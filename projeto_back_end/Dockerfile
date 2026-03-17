# Imagem de producao com Python 3.12 (LTS, suporte ate 2028).
# Nota: o ambiente local de desenvolvimento usa Python 3.14, o que e valido.
FROM python:3.12-slim

# Define o diretório de trabalho
WORKDIR /app

# Copia e instala dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY app ./app

# Evita buffering de output do Python (logs aparecem imediatamente)
ENV PYTHONUNBUFFERED=1

# Inicia a aplicação
# ${PORT:-8000} usa a variável PORT do Render, ou 8000 como fallback
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]