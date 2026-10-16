#!/usr/bin/env python3
"""Figura temporal de UMA execucao com perturbacao (C4 a C7) - para a secao 4.6.

Tres paineis com eixo de tempo comum (sem misturar unidades no mesmo eixo):
  1) P95 do cliente (k6, respostas corretas) por janela de 5 s, em ms
  2) Vazao com sucesso (RPS) por janela de 5 s
  3) Recurso do host exportado do Prometheus (CPU %, RAM usada % ou nenhum)
Faixa sombreada = intervencao (horarios gravados pelo servidor, corrigidos pelo offset).
Formato para impressao: tema claro, virgula decimal, PNG 300 dpi.
Requer matplotlib (no WSL: sudo apt install python3-matplotlib).
Uso: python3 scripts/plot_run.py <pasta_da_execucao> [--recurso cpu|mem|nenhum] [--saida fig.png]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_run import parse_ts  # noqa: E402

virgula = FuncFormatter(lambda v, _p: f"{v:g}".replace(".", ","))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--recurso", choices=["cpu", "mem", "nenhum"], default="cpu")
    ap.add_argument("--saida")
    a = ap.parse_args()
    d = a.run_dir
    man = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    t0 = parse_ts(man["k6_start_utc"])
    off = float(man.get("clock_offset_s") or 0)
    win = list(csv.DictReader(open(os.path.join(d, "analysis", "windows.csv"), encoding="utf-8")))
    x = [float(w["t_rel_s"]) for w in win]
    p95 = [float(w["p95_ms"]) if w["p95_ms"] not in ("", "None") else float("nan") for w in win]
    rps = [float(w["rps_sucesso"]) for w in win]

    ev = {}
    evp = os.path.join(d, "events-server.csv")
    if os.path.exists(evp):
        for r in csv.DictReader(open(evp, encoding="utf-8")):
            ev[r["event"]] = parse_ts(r["timestamp_utc"]) - off - t0

    n = 3 if a.recurso != "nenhum" else 2
    fig, axs = plt.subplots(n, 1, figsize=(7.5, 2.1 * n + 0.6), sharex=True)
    axs[0].plot(x, p95, color="#1f4e79", lw=1.4)
    axs[0].set_ylabel("P95 cliente (ms)")
    axs[1].plot(x, rps, color="#2e7d32", lw=1.4)
    axs[1].set_ylabel("Vazão c/ sucesso (RPS)")
    axs[0].set_ylim(bottom=0)
    axs[1].set_ylim(bottom=0)  # eixos a partir de zero: nao exageram diferencas
    if a.recurso != "nenhum":
        name = "cpu_host_pct" if a.recurso == "cpu" else "mem_used_pct"
        pj = os.path.join(d, "server", f"prom-{name}.json")
        if os.path.exists(pj):
            res = json.load(open(pj))["data"]["result"]
            if res:
                xs = [float(v[0]) - off - t0 for v in res[0]["values"]]
                ys = [float(v[1]) for v in res[0]["values"]]
                axs[2].plot(xs, ys, color="#b71c1c", lw=1.4)
        axs[2].set_ylabel("CPU do host (%)" if a.recurso == "cpu" else "RAM usada (%)")
        axs[2].set_ylim(0, 100)
    for ax in axs:
        ax.grid(alpha=0.3)
        ax.yaxis.set_major_formatter(virgula)
        if "stress_start" in ev and "stress_end" in ev:
            ax.axvspan(ev["stress_start"], ev["stress_end"], color="#f9a825", alpha=0.25, lw=0)
    axs[-1].set_xlim(0, max(x) + 5 if x else 1)
    axs[-1].set_xlabel("Tempo desde o início da carga (s)")
    axs[-1].xaxis.set_major_formatter(virgula)
    fig.tight_layout()
    out = a.saida or os.path.join(d, "analysis", f"figura-{man['run_id']}.png")
    fig.savefig(out, dpi=300)
    print(f"figura salva em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
