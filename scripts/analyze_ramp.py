#!/usr/bin/env python3
"""Analisa a rampa de capacidade (experiments/k6/ramp.js) por degrau.

Cada degrau = 10 s de transicao (descartados) + STEP_S segundos estaveis (analisados).
Joelho sugerido = primeiro degrau com P95 >= 2x o P95 do 1o degrau, OU falhas > 0,
OU dropped_iterations > 0. A escolha final do joelho e registrada no protocolo.
Uso: python3 scripts/analyze_ramp.py <pasta_com_k6-raw.json> <k6_start_utc> [STEPS] [STEP_S]
  ex.: python3 scripts/analyze_ramp.py runs/pilot/ramp-... 2026-10-20T18:00:00.123+00:00 10,20,40,60,80,100,120 60
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_run import load_k6, nearest_rank, parse_ts  # noqa: E402

d, start = sys.argv[1], parse_ts(sys.argv[2])
steps = [float(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "10,20,40,60,80,100,120").split(",")]
step_s = float(sys.argv[4]) if len(sys.argv) > 4 else 60.0
attempts, oks, dropped = load_k6(os.path.join(d, "k6-raw.json"))
print("degrau_rps,inicio_s,N_corretas,vazao_ok_rps,p95_ms,p99_ms,falhas,dropped,joelho")
base = None
knee_found = False
for i, rps in enumerate(steps):
    a = start + i * (step_s + 10) + 10
    b = a + step_s
    lat = [ms for t, ms in oks if a <= t < b]
    fails = sum(f for t, f in attempts if a <= t < b)
    drp = sum(n for t, n in dropped if a <= t < b)
    p95 = nearest_rank(lat, 0.95)
    p99 = nearest_rank(lat, 0.99)
    if base is None:
        base = p95
    knee = (not knee_found) and ((p95 is not None and base and p95 >= 2 * base) or fails > 0 or drp > 0)
    knee_found = knee_found or knee
    print(f"{rps:g},{a - start:.0f},{len(lat)},{len(lat) / step_s:.2f},{p95},{p99},{fails},{int(drp)},{'<- JOELHO' if knee else ''}")
