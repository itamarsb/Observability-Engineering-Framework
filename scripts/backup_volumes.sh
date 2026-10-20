#!/usr/bin/env bash
# Backup offline dos volumes do projeto Compose; requer servidor, Docker funcional.
# Os servicos sempre recebem tentativa de religacao, mesmo em falha ou interrupcao.
set -euo pipefail
PROJECT="${PROJECT:-tcc2}"
DEST="${1:-$HOME/tcc2-backup/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$DEST"
DEST="$(realpath "$DEST")"
NEEDS_RESTART=1
restart() {
  if [[ "$NEEDS_RESTART" -eq 1 ]]; then
    echo "Tentando religar os servicos apos backup/interrupcao..." >&2
    docker compose -p "$PROJECT" start || echo "ATENCAO: religacao falhou; verificar docker compose -p "$PROJECT" ps" >&2
  fi
}
trap restart EXIT
trap 'exit 130' INT TERM
docker compose -p "$PROJECT" stop
mapfile -t VOLUMES < <(docker volume ls -q --filter "label=com.docker.compose.project=${PROJECT}")
if [[ ${#VOLUMES[@]} -eq 0 ]]; then
  echo "ERRO: nenhum volume localizado para o projeto ${PROJECT}" >&2
  exit 2
fi
for v in "${VOLUMES[@]}"; do
  echo "copiando $v"
  docker run --rm --entrypoint /bin/sh -v "$v":/v:ro -v "$DEST":/b \
    prom/prometheus:v3.15.0 -c "tar czf /b/${v}.tgz -C /v ."
done
( cd "$DEST" && sha256sum ./*.tgz > checksums.sha256 && sha256sum -c checksums.sha256 )
docker compose -p "$PROJECT" start
NEEDS_RESTART=0
trap - EXIT
echo "Backup em $DEST"; ls -lh "$DEST"
