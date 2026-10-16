#!/usr/bin/env python3
"""Figura de resposta a carga (secao 4.5): C1, C0, C2 e C3, fase util.

Painel 1: P95 e P99 do cliente (ms) - um ponto por repeticao e a mediana (traco).
Painel 2: vazao com sucesso (RPS) - um ponto por repeticao e a mediana.
Unidades em paineis separados; virgula decimal; PNG 300 dpi.
Uso: python3 scripts/plot_load.py results/processed/summary-runs.csv [saida.png]
"""
import csv
import statistics
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

ORDER = ["C1", "C0", "C2", "C3"]
src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else "results/charts/figura-carga.png"
rows = [r for r in csv.DictReader(open(src, encoding="utf-8")) if r["fase"] == "util" and r["cenario"] in ORDER]
virg = FuncFormatter(lambda v, _p: f"{v:g}".replace(".", ","))
fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.5, 3.2))
for i, cen in enumerate(ORDER):
    rs = [r for r in rows if r["cenario"] == cen]
    if not rs:
        continue
    for key, color, dx in (("p95_ms", "#1f4e79", -0.12), ("p99_ms", "#c2410c", 0.12)):
        vals = [float(r[key]) for r in rs if r[key] not in ("", "None")]
        a1.scatter([i + dx] * len(vals), vals, s=14, color=color, zorder=3)
        if vals:
            a1.hlines(statistics.median(vals), i + dx - 0.1, i + dx + 0.1, color=color, lw=2)
    v = [float(r["vazao_sucesso_rps"]) for r in rs]
    a2.scatter([i] * len(v), v, s=14, color="#15803d", zorder=3)
    a2.hlines(statistics.median(v), i - 0.12, i + 0.12, color="#15803d", lw=2)
for ax, yl in ((a1, "Latência do cliente (ms)"), (a2, "Vazão com sucesso (RPS)")):
    ax.set_xticks(range(len(ORDER)), ORDER)
    ax.set_xlim(-0.5, len(ORDER) - 0.5)
    ax.set_ylim(bottom=0)  # eixo a partir de zero: nao exagera diferencas
    ax.set_ylabel(yl)
    ax.grid(alpha=0.3, axis="y")
    ax.yaxis.set_major_formatter(virg)
a1.scatter([], [], color="#1f4e79", s=14, label="P95")
a1.scatter([], [], color="#c2410c", s=14, label="P99")
a1.legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig(out, dpi=300)
print(f"figura salva em {out}")
