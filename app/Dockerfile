# Imagem da API do TCC2. Depois do 1o build, fixe a base por digest:
#   docker image inspect python:3.12-slim --format '{{index .RepoDigests 0}}'
# e troque a linha FROM por: FROM python:3.12-slim@sha256:<digest>
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY main.py telemetry.py ./

RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8000

# 1 worker (fixo em todas as repeticoes); sem reload; sem access log (o evento
# request_completed ja registra cada requisicao). keep-alive > keepalive do NGINX (60 s).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--no-access-log", "--timeout-keep-alive", "75"]
