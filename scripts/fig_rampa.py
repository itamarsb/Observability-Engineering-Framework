#!/usr/bin/env python3
"""Figura C10 - rampa de calibracao e capacidade operacional (pasta criada por run_ramp.sh).

Paineis, com o degrau ofertado (RPS) no eixo x:
  (a) Oferta x vazao com sucesso por degrau (janela estavel de cada degrau)
  (b) P95 e P99 do cliente por degrau + referencia de 2x o P95 do 1o degrau (regra do joelho)
  (c) CPU media do gerador (vmstat no WSL) e do servidor (Prometheus) + dropped_iterations
O joelho sugerido segue analyze_ramp.py; a escolha final e do operador (protocol-v1.md).
Se a CPU do gerador estiver alta perto do joelho, a limitacao pode ser do GERADOR,
e nao do servidor: a figura mostra as duas CPUs justamente para essa verificacao.
Uso: python3 scripts/fig_rampa.py runs/pilot/RAMP-<UTC> [--saida results/charts/C10-rampa.png]
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import figstyle as fs  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from analyze_ramp import analisar  # noqa: E402
from analyze_run import parse_ts  # noqa: E402
from run_context import ler_json, ler_vmstat  # noqa: E402

VERSION = "fig_rampa/1.0"


def media_no_intervalo(pontos, a, b):
    vals = [v for t, v in pontos if a <= t < b]
    return statistics.fmean(vals) if vals else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ramp_dir")
    ap.add_argument("--saida", default="results/charts/C10-rampa.png")
    ap.add_argument("--altura-cm", type=float, default=11.0)
    a = ap.parse_args()
    d = a.ramp_dir
    man = ler_json(os.path.join(d, "manifest.json"))
    t0 = parse_ts(man["k6_start_utc"])
    off = float(man.get("clock_offset_s") or 0)
    steps = [float(s) for s in man["steps"]]
    step_s = float(man["step_s"])
    rows = analisar(d, t0, steps, step_s)
    entradas = [os.path.join(d, "manifest.json"), os.path.join(d, "k6-raw.json")]
    sintetico = bool(man.get("synthetic")) or man.get("kind") == "synthetic" or man["run_id"].startswith("SINT")

    vm_p = os.path.join(d, "notebook-vmstat.txt")
    gerador = [(t - t0, v) for t, v in ler_vmstat(vm_p)] if os.path.exists(vm_p) else []
    if gerador:
        entradas.append(vm_p)
    srv = []
    pj = os.path.join(d, "server", "prom-cpu_host_pct.json")
    if os.path.exists(pj):
        res = ler_json(pj).get("data", {}).get("result", [])
        if res:
            srv = [(float(ts) - off - t0, float(v)) for ts, v in res[0]["values"] if v not in ("NaN",)]
            entradas.append(pj)
    for r in rows:
        r["cpu_gerador"] = media_no_intervalo(gerador, r["inicio_s"], r["fim_s"])
        r["cpu_servidor"] = media_no_intervalo(srv, r["inicio_s"], r["fim_s"])

    x = [r["degrau_rps"] for r in rows]
    joelho = next((r["degrau_rps"] for r in rows if r["joelho"]), None)
    fs.aplicar_estilo()
    fig, (a1, a2, a3) = plt.subplots(3, 1, sharex=True, figsize=fs.cm(fs.LARGURA_CM, a.altura_cm))

    a1.plot(x, x, color=fs.COR["oferta"], ls="--", marker="o", ms=3, lw=1.0, label="Carga ofertada (degrau)")
    a1.plot(x, [r["vazao_ok_rps"] for r in rows], color=fs.COR["vazao"], marker="s", ms=3.2,
            label="Vazão com sucesso")
    a1.set_ylabel("Requisições/s\n(RPS)")
    a1.legend(loc="upper left")

    a2.plot(x, [r["p95_ms"] for r in rows], color=fs.COR["p95"], marker="o", ms=3, label="P95")
    a2.plot(x, [r["p99_ms"] for r in rows], color=fs.COR["p99"], marker="s", ms=3, label="P99")
    if rows and rows[0]["p95_ms"]:
        ref = 2 * rows[0]["p95_ms"]
        a2.axhline(ref, color=fs.COR["limite"], ls=":", lw=0.9)
        a2.text(0.01, ref, f" 2 × P95 do 1º degrau = {fs.num_br(round(ref, 1))} ms",
                transform=a2.get_yaxis_transform(), va="bottom", fontsize=6, color=fs.COR["limite"])
    a2.set_ylabel("Latência do\ncliente (ms)")
    a2.legend(loc="upper left")

    if gerador:
        a3.plot(x, [r["cpu_gerador"] for r in rows], color=fs.COR["cpu_gerador"], marker="o", ms=3,
                label="CPU do gerador (WSL2, vmstat)")
    if srv:
        a3.plot(x, [r["cpu_servidor"] for r in rows], color=fs.COR["cpu"], marker="s", ms=3,
                label="CPU do servidor (Prometheus)")
    a3.set_ylim(0, 105)
    a3.set_ylabel("CPU média\nno degrau (%)")
    a3.set_xlabel("Degrau de carga ofertada (RPS)")
    b3 = a3.twinx()
    larg = min(b - a for a, b in zip(x, x[1:])) * 0.35 if len(x) > 1 else 4
    b3.bar(x, [r["dropped"] for r in rows], width=larg, color=fs.COR["dropped"], alpha=0.35,
           label="dropped_iterations", zorder=1)
    b3.set_ylabel("dropped_iterations", color=fs.COR["dropped"])
    b3.spines["right"].set_visible(True)
    b3.grid(False)
    b3.set_ylim(0, max([r["dropped"] for r in rows] + [1]) * 1.4)
    h1, l1 = a3.get_legend_handles_labels()
    h2, l2 = b3.get_legend_handles_labels()
    a3.legend(h1 + h2, l1 + l2, loc="upper left")

    for ax in (a1, a2, a3):
        ax.grid(axis="x", visible=False)
    for ax in (a1, a2):
        ax.set_ylim(bottom=0)
    if joelho is not None:
        for ax in (a1, a2, a3):
            ax.axvspan(joelho - larg, max(x) + larg, color="#fbe9ec", lw=0, zorder=0)
        a1.text(joelho, 0.97, f" joelho sugerido: {fs.num_br(joelho)} RPS", transform=a1.get_xaxis_transform(),
                ha="left", va="top", fontsize=6.5, color=fs.COR["limite"], weight="bold")
    a3.set_xticks(x)
    fs.formatar_eixos((a1, a2, a3, b3), eixo_x=True)
    falt = []
    if not gerador:
        falt.append("CPU do gerador indisponível (gravar com: TZ=UTC vmstat -n -t 5)")
    if not srv:
        falt.append("CPU do servidor indisponível (server/prom-cpu_host_pct.json)")
    partes = [f"run_id {man['run_id']}", f"{len(steps)} degraus de {fs.num_br(step_s)} s "
              "(10 s de transição descartados)",
              "joelho: P95 ≥ 2 × P95 do 1º degrau, falhas ou dropped_iterations > 0"] + falt
    fig.align_ylabels((a1, a2, a3))
    base = fs.rodape(fig, partes, a.altura_cm)
    fig.tight_layout(pad=0.4, h_pad=0.6, rect=(0, base, 1, fs.topo(a.altura_cm, sintetico)))
    fs.salvar(fig, a.saida, VERSION, entradas,
              {"run_id": man["run_id"], "steps": steps, "step_s": step_s, "joelho_sugerido": joelho,
               "degraus": [{k: r[k] for k in ("degrau_rps", "vazao_ok_rps", "p95_ms", "p99_ms", "dropped",
                                               "cpu_gerador", "cpu_servidor")} for r in rows]}, sintetico)
    with open(os.path.join(os.path.dirname(os.path.abspath(a.saida)),
                           os.path.basename(a.saida).rsplit(".", 1)[0] + "-degraus.csv"), "w",
              newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
