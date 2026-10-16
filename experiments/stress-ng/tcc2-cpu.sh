#!/usr/bin/env bash
# /usr/local/sbin/tcc2-cpu.sh  (dono root, modo 755) - chamado via sudo pelo orquestrador.
# Contencao de CPU no HOST inteiro: stress-ng em todas as CPUs (--cpu 0 = 8 threads no i7-2600).
# Uso: sudo /usr/local/sbin/tcc2-cpu.sh <duracao_s> <carga_pct>
# Saida padrao (stdout) = CSV de eventos com horario do SERVIDOR (events-server.csv).
set -euo pipefail
DUR="${1:-180}"
LOAD="${2:-90}"
[[ "$DUR" =~ ^[0-9]+$ && "$LOAD" =~ ^[0-9]+$ ]] || { echo "parametros invalidos" >&2; exit 2; }
(( DUR >= 10 && DUR <= 900 && LOAD >= 1 && LOAD <= 100 )) || { echo "fora dos limites" >&2; exit 2; }
ts() { python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).isoformat(timespec="microseconds"))'; }
if systemctl is-active --quiet tcc2-cpu; then echo "tcc2-cpu ja esta ativa" >&2; exit 3; fi

echo "event,timestamp_utc,detail"
echo "stress_start,$(ts),cpu=0 cpu-load=${LOAD} timeout=${DUR}s"
rc=0
systemd-run --unit=tcc2-cpu --collect --wait --pipe --quiet \
  -p RuntimeMaxSec="$((DUR + 10))s" \
  stress-ng --cpu 0 --cpu-load "$LOAD" --timeout "${DUR}s" --metrics-brief 1>&2 || rc=$?
echo "stress_end,$(ts),rc=${rc}"
exit "$rc"
