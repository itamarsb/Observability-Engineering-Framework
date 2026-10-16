#!/usr/bin/env bash
# Copia os volumes do Compose (Prometheus, Loki, Tempo, Grafana) com os servicos PARADOS.
# Rodar no SERVIDOR, na raiz do repositorio, depois da campanha (e antes da reimplantacao).
# Usa a imagem do Prometheus (ja baixada) so como "caixa" com tar; nao altera os volumes (:ro).
set -euo pipefail
PROJECT="${PROJECT:-tcc2}"
DEST="${1:-$HOME/tcc2-backup/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$DEST"
docker compose stop
for v in $(docker volume ls -q --filter "label=com.docker.compose.project=${PROJECT}"); do
  echo "copiando $v"
  docker run --rm --entrypoint /bin/sh -v "$v":/v:ro -v "$DEST":/b prom/prometheus:v3.15.0 \
    -c "tar czf /b/${v}.tgz -C /v ."
done
docker compose start
( cd "$DEST" && sha256sum ./*.tgz > checksums.sha256 )
echo "Backup em $DEST"; ls -lh "$DEST"
