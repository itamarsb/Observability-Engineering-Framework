#!/usr/bin/env bash
# /usr/local/sbin/tcc2-mem.sh  (dono root, modo 755) - chamado via sudo pelo orquestrador.
# Pressao de memoria com teto rigido (MemoryMax) e sem swap para a unidade (MemorySwapMax=0).
# Uso: sudo /usr/local/sbin/tcc2-mem.sh <duracao_s> <vm_bytes ex.: 4G> <teto ex.: 5G>
# Regra de seguranca: teto <= 6G e <= 50% do MemAvailable de repouso; manter >= 2 GiB livres.
set -euo pipefail
DUR="${1:-180}"
BYTES="${2:-2G}"
MAXMEM="${3:-3G}"
[[ "$DUR" =~ ^[0-9]+$ && "$BYTES" =~ ^[0-9]+[MG]$ && "$MAXMEM" =~ ^[0-9]+[MG]$ ]] \
  || { echo "parametros invalidos" >&2; exit 2; }
(( DUR >= 10 && DUR <= 900 )) || { echo "duracao fora dos limites" >&2; exit 2; }
ts() { python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).isoformat(timespec="microseconds"))'; }
if systemctl is-active --quiet tcc2-mem; then echo "tcc2-mem ja esta ativa" >&2; exit 3; fi

echo "event,timestamp_utc,detail"
echo "stress_start,$(ts),vm=1 vm-bytes=${BYTES} MemoryMax=${MAXMEM} timeout=${DUR}s"
rc=0
systemd-run --unit=tcc2-mem --collect --wait --pipe --quiet \
  -p RuntimeMaxSec="$((DUR + 10))s" -p MemoryMax="$MAXMEM" -p MemorySwapMax=0 \
  stress-ng --vm 1 --vm-bytes "$BYTES" --vm-keep --timeout "${DUR}s" --metrics-brief 1>&2 || rc=$?
echo "stress_end,$(ts),rc=${rc}"
exit "$rc"
