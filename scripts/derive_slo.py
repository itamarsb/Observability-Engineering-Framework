#!/usr/bin/env python3
"""Deriva as metas de latencia (SLO) a partir dos pilotos C0, pela regra da secao 3.3:
meta = 2 x mediana do P95 (ou P99) da fase util dos pilotos C0, arredondada PARA CIMA
em multiplos de 25 ms. Sem --gravar, so imprime. Com --gravar (pede confirmacao), grava
SLO_P95_MS/SLO_P99_MS em slo.env e a linha "Metas (SLO)" do protocol-v1.md. Recusa gravar
depois do congelamento (nao altere metas depois de ver resultados).

Uso: python3 scripts/derive_slo.py runs/pilot [--cenario C0] [--multiplo 25] [--gravar] [--sim]
Considera as pastas <cenario>-*/analysis/phases.csv; execucoes com "INVALIDA" no notes.md
sao listadas e descartadas.
"""

from __future__ import annotations

import argparse
import glob
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocolo as pr  # noqa: E402
from run_context import ler_csv, ler_texto  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta", nargs="?", default="runs/pilot")
    ap.add_argument("--cenario", default="C0")
    ap.add_argument("--multiplo", type=float, default=25.0)
    ap.add_argument("--gravar", action="store_true", help="grava slo.env e o protocolo (pede confirmacao)")
    ap.add_argument("--sim", action="store_true", help="confirma sem perguntar")
    ap.add_argument("--slo", default=os.path.join(pr.CENARIOS_DIR, "slo.env"))
    ap.add_argument("--protocolo", default=pr.PROTOCOLO)
    ap.add_argument("--common", default=pr.COMMON)
    a = ap.parse_args()
    p95s, p99s = [], []
    for run in sorted(glob.glob(os.path.join(a.pasta, f"{a.cenario}-*"))):
        notes = os.path.join(run, "notes.md")
        if os.path.exists(notes) and "INVALIDA" in ler_texto(notes):
            print(f"  descartada (INVALIDA): {os.path.basename(run)}")
            continue
        ph = os.path.join(run, "analysis", "phases.csv")
        if not os.path.exists(ph):
            print(f"  sem analise: {os.path.basename(run)}")
            continue
        for r in ler_csv(ph):
            if r["fase"] == "util" and r["p95_ms"] not in ("", "None"):
                p95s.append(float(r["p95_ms"]))
                p99s.append(float(r["p99_ms"]))
                print(f"  {os.path.basename(run)}: P95={r['p95_ms']} ms  P99={r['p99_ms']} ms")
    if not p95s:
        print(f"nenhum piloto {a.cenario} analisado em {a.pasta}", file=sys.stderr)
        return 1
    m = a.multiplo
    regra = lambda v: math.ceil(2 * v / m) * m  # noqa: E731
    med95, med99 = statistics.median(p95s), statistics.median(p99s)
    print(f"\npilotos {a.cenario} considerados: {len(p95s)}")
    print(f"mediana P95 = {med95:.3f} ms -> 2x = {2 * med95:.3f} -> meta = {regra(med95):g} ms")
    print(f"mediana P99 = {med99:.3f} ms -> 2x = {2 * med99:.3f} -> meta = {regra(med99):g} ms")
    m95, m99 = regra(med95), regra(med99)
    print(f"\nSLO_P95_MS={m95:g}\nSLO_P99_MS={m99:g}")
    if not a.gravar:
        print("\n(nada foi gravado; para gravar:  python3 scripts/derive_slo.py runs/pilot --gravar)")
        return 0
    if pr.protocolo_congelado(a.common):
        print("RECUSADO: protocolo ja congelado; metas nao podem mudar depois do congelamento.", file=sys.stderr)
        return 3
    if not pr.confirmar(f"Gravar P95 <= {m95:g} ms e P99 <= {m99:g} ms em slo.env e no protocolo?", a.sim):
        print("nada foi gravado")
        return 0
    pr.gravar_env(a.slo, "SLO_P95_MS", f"{m95:g}")
    pr.gravar_env(a.slo, "SLO_P99_MS", f"{m99:g}")
    atual = pr.linha_protocolo(a.protocolo, "Metas (SLO)") or ""
    resto = atual.split("regra:", 1)[1] if "regra:" in atual else " 2x piloto C0, multiplo de 25 ms)"
    pr.definir_linha_protocolo(
        a.protocolo, "Metas (SLO)",
        f"P95 <= {m95:g} ms; P99 <= {m99:g} ms (medianas dos {len(p95s)} pilotos {a.cenario}: "
        f"P95 {med95:.1f} ms e P99 {med99:.1f} ms; regra:{resto}")
    print(f"gravado: {a.slo} e linha 'Metas (SLO)' de {a.protocolo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
