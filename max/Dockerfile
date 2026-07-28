# ---------- Build ----------
FROM python:3.12-slim AS builder

# Dependências de sistema para compilar pacotes com extensões em C (numba, llvmlite, spacy, blis, thinc, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Ambiente virtual isolado, copiado depois para a imagem final
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Runtime ----------
FROM python:3.12-slim

# libmagic é necessário em tempo de execução pelo python-magic (usado pelo unstructured)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Reaproveita o ambiente virtual já com as dependências instaladas
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copia o código da aplicação (.dockerignore evita levar .venv, .env, __pycache__ etc.)
COPY . .

EXPOSE 7083

# worker.py sobe o HTTP (healthcheck + POST /rag/ingest, porta PORT) e consome
# a fila genérica task.agent.generic.create no RabbitMQ (qualquer agente que
# não seja atlas/axel), publicando em outbound.message.send ou
# desk.ticket.create.
CMD ["python", "worker.py"]
