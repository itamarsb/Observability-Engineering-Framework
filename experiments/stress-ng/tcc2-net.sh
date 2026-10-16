#!/usr/bin/env bash
# /usr/local/sbin/tcc2-net.sh  (dono root, modo 755) - chamado via sudo pelo orquestrador.
# Atraso artificial (tc netem) SOMENTE na interface eth0 do namespace de rede do conteiner
# NGINX. Nao toca na interface fisica do servidor (SSH e OTLP nao sao afetados).
# Uso: sudo /usr/local/sbin/tcc2-net.sh <duracao_s> <atraso_ms>
# Pre-requisito (uma vez): sudo modprobe sch_netem  (se faltar: linux-modules-extra-$(uname -r))
set -euo pipefail
DUR="${1:-180}"
DELAY="${2:-100}"
PROJECT="${PROJECT:-tcc2}"
[[ "$DUR" =~ ^[0-9]+$ && "$DELAY" =~ ^[0-9]+$ ]] || { echo "parametros invalidos" >&2; exit 2; }
(( DUR >= 10 && DUR <= 900 && DELAY >= 1 && DELAY <= 1000 )) || { echo "fora dos limites" >&2; exit 2; }
ts() { python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).isoformat(timespec="microseconds"))'; }

CID=$(docker ps -q --filter "label=com.docker.compose.project=${PROJECT}" \
                   --filter "label=com.docker.compose.service=nginx")
[[ -n "$CID" && $(wc -l <<<"$CID") -eq 1 ]] || { echo "conteiner nginx nao encontrado (ou mais de um)" >&2; exit 3; }
PID=$(docker inspect -f '{{.State.Pid}}' "$CID")
[[ "$PID" =~ ^[0-9]+$ && "$PID" -gt 1 ]] || { echo "PID invalido" >&2; exit 3; }

echo "# antes:" >&2
nsenter -t "$PID" -n ip -br link >&2
nsenter -t "$PID" -n tc qdisc show dev eth0 >&2
if nsenter -t "$PID" -n tc qdisc show dev eth0 | grep -q netem; then
  echo "ja existe netem em eth0 - abortando sem alterar" >&2; exit 4
fi

cleanup() { nsenter -t "$PID" -n tc qdisc del dev eth0 root 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "event,timestamp_utc,detail"
nsenter -t "$PID" -n tc qdisc add dev eth0 root netem delay "${DELAY}ms"
echo "stress_start,$(ts),netem delay=${DELAY}ms nginx_pid=${PID}"
nsenter -t "$PID" -n tc -s qdisc show dev eth0 >&2
sleep "$DUR"
nsenter -t "$PID" -n tc -s qdisc show dev eth0 >&2
cleanup
echo "stress_end,$(ts),netem removido"
trap - EXIT INT TERM
echo "# depois:" >&2
nsenter -t "$PID" -n tc qdisc show dev eth0 >&2
