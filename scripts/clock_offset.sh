#!/usr/bin/env bash
# Mede a diferenca de relogio entre o servidor e o notebook (WSL), via SSH.
# offset = relogio_servidor - relogio_notebook (segundos). Use a linha de menor RTT:
# a incerteza e de no maximo metade do RTT. Limite do protocolo: |offset| <= 1 s.
# Uso: scripts/clock_offset.sh itamar@10.10.10.1
set -euo pipefail
SERVER="${1:?uso: clock_offset.sh usuario@ip}"
now() { python3 -c 'import time; print(f"{time.time():.6f}")'; }
echo "medida,offset_s,rtt_s"
for i in 1 2 3 4 5; do
  t0=$(now)
  r=$(ssh -o BatchMode=yes "$SERVER" "python3 -c 'import time; print(f\"{time.time():.6f}\")'")
  t1=$(now)
  python3 -c "t0,r,t1=$t0,$r,$t1; print(f'$i,{r-(t0+t1)/2:+.4f},{t1-t0:.4f}')"
done
