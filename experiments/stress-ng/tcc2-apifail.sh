#!/usr/bin/env bash
# /usr/local/sbin/tcc2-apifail.sh  (dono root, modo 755) - C7 OPCIONAL (falha controlada).
# Para o conteiner da API por <duracao_s> e o religa. O NGINX continua ativo (devolve 502).
# A API tem IP fixo na rede do Compose, entao o NGINX volta a encontra-la apos o start.
# Uso: sudo /usr/local/sbin/tcc2-apifail.sh <duracao_s>
set -euo pipefail
DUR="${1:-60}"
PROJECT="${PROJECT:-tcc2}"
[[ "$DUR" =~ ^[0-9]+$ ]] && (( DUR >= 10 && DUR <= 300 )) || { echo "duracao invalida" >&2; exit 2; }
ts() { python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).isoformat(timespec="microseconds"))'; }
CID=$(docker ps -q --filter "label=com.docker.compose.project=${PROJECT}" \
                   --filter "label=com.docker.compose.service=api")
[[ -n "$CID" && $(wc -l <<<"$CID") -eq 1 ]] || { echo "conteiner api nao encontrado" >&2; exit 3; }

restart_api() { docker start "$CID" >/dev/null 2>&1 || true; }
trap restart_api EXIT INT TERM
echo "event,timestamp_utc,detail"
docker stop -t 2 "$CID" >&2
echo "stress_start,$(ts),api parada"
sleep "$DUR"
docker start "$CID" >&2
echo "stress_end,$(ts),api religada"
trap - EXIT INT TERM
