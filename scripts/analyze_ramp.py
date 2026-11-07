#!/usr/bin/env python3
"""Analisa a rampa de capacidade (experiments/k6/ramp.js) por degrau.

Cada degrau = 10 s de transicao (descartados) + STEP_S segundos estaveis (analisados).
Joelho sugerido = primeiro degrau com P95 >= 2x o P95 do 1o degrau, OU falhas > 0,
OU dropped_iterations > 0. A escolha final do joelho e registrada no protocolo.

Uso (pasta criada por scripts/run_ramp.sh: horario, degraus e duracao lidos do manifest.json):
  python3 scripts/analyze_ramp.py runs/pilot/RAMP-...
Uso manual (compativel com a versao anterior):
  python3 scripts/analyze_ramp.py <pasta_com_k6-raw.json> <k6_start_utc> [STEPS] [STEP_S]
  ex.: python3 scripts/analyze_ramp.py runs/pilot/ramp-... 2026-10-20T18:00:00.123+00:00 10,20,40,60,80,100,120 60
Saida: tabela na tela e <pasta>/analysis/ramp-steps.csv (usado por fig_rampa.py).
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_run import load_k6, nearest_rank, parse_ts  # noqa: E402
from run_context import ler_json  # noqa: E402

TRANSICAO_S = 10.0
CAMPOS = ["degrau_rps", "inicio_s", "fim_s", "tentativas", "N_corretas", "vazao_observada_rps", "vazao_ok_rps",
          "p95_ms", "p99_ms", "falhas", "dropped", "joelho"]


def analisar(d: str, start: float, steps: list[float], step_s: float) -> list[dict]:
    attempts, oks, dropped = load_k6(os.path.join(d, "k6-raw.json"))
    rows, base, knee_found = [], None, False
    for i, rps in enumerate(steps):
        a = start + i * (step_s + TRANSICAO_S) + TRANSICAO_S
        b = a + step_s
        lat = [ms for t, ms in oks if a <= t < b]
        att = [f for t, f in attempts if a <= t < b]
        fails = sum(att)
        drp = sum(n for t, n in dropped if a <= t < b)
        p95 = nearest_rank(lat, 0.95)
        p99 = nearest_rank(lat, 0.99)
        if base is None:
            base = p95
        knee = (not knee_found) and ((p95 is not None and base and p95 >= 2 * base) or fails > 0 or drp > 0)
        knee_found = knee_found or knee
        rows.append({"degrau_rps": rps, "inicio_s": round(a - start, 1), "fim_s": round(b - start, 1),
                     "tentativas": len(att), "N_corretas": len(lat),
                     "vazao_observada_rps": round(len(att) / step_s, 2), "vazao_ok_rps": round(len(lat) / step_s, 2),
                     "p95_ms": p95, "p99_ms": p99, "falhas": fails, "dropped": int(drp), "joelho": knee})
    return rows


def main() -> int:
    d = sys.argv[1]
    man_p = os.path.join(d, "manifest.json")
    man = ler_json(man_p) if os.path.exists(man_p) else {}
    if len(sys.argv) > 2:
        start = parse_ts(sys.argv[2])
    elif "k6_start_utc" in man:
        start = parse_ts(man["k6_start_utc"])
    else:
        print("informe k6_start_utc ou use uma pasta com manifest.json (scripts/run_ramp.sh)", file=sys.stderr)
        return 2
    if len(sys.argv) > 3:
        steps = [float(x) for x in sys.argv[3].split(",")]
    else:
        steps = [float(x) for x in man.get("steps", [10, 20, 40, 60, 80, 100, 120])]
    step_s = float(sys.argv[4]) if len(sys.argv) > 4 else float(man.get("step_s", 60))
    rows = analisar(d, start, steps, step_s)
    print("degrau_rps,inicio_s,N_corretas,vazao_ok_rps,p95_ms,p99_ms,falhas,dropped,joelho")
    for r in rows:
        print(f"{r['degrau_rps']:g},{r['inicio_s']:.0f},{r['N_corretas']},{r['vazao_ok_rps']:.2f},{r['p95_ms']},"
              f"{r['p99_ms']},{r['falhas']},{r['dropped']},{'<- JOELHO' if r['joelho'] else ''}")
    os.makedirs(os.path.join(d, "analysis"), exist_ok=True)
    with open(os.path.join(d, "analysis", "ramp-steps.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
