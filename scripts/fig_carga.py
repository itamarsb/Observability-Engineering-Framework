#!/usr/bin/env python3
"""Figura 3 do artigo - cenarios de carga (C0, C2, C3), fase util, n repeticoes validas.

Paineis (unidades nunca misturadas no mesmo eixo):
  (a) Latencia do cliente: P95 e P99 - mediana com barra [minimo-maximo] das repeticoes
  (b) Oferta x vazao: taxa ofertada (manifesto) e vazao com sucesso - mediana [min-max]
  (c) Erro composto (%) - mediana com barra [min-max]
Os percentis de cada repeticao NAO sao promediados: a mediana e o intervalo descrevem
as n repeticoes (Apendice A). Cenarios ordenados pela taxa ofertada.

Entrada: results/processed/summary-runs.csv (scripts/consolidate.py), que ja exclui
execucoes nao aprovadas (notes.md sem "Classificacao final: VALIDA").
Uso: python3 scripts/fig_carga.py results/processed/summary-runs.csv \
        [--saida results/charts/fig03-carga.png] [--altura-cm 5.5] [--cenarios C1,C0,C2,C3]
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import figstyle as fs  # noqa: E402
from run_context import ler_csv  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

VERSION = "fig_carga/1.0"


def num(v):
    return None if v in (None, "", "None") else float(v)


def resumo(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, None, None
    return statistics.median(vals), min(vals), max(vals)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("summary_runs")
    ap.add_argument("--saida", default="results/charts/fig03-carga.png")
    ap.add_argument("--altura-cm", type=float, default=5.5)
    ap.add_argument("--cenarios", default="C0,C2,C3")
    a = ap.parse_args()

    cens = a.cenarios.split(",")
    rows = [r for r in ler_csv(a.summary_runs)
            if r["fase"] == "util" and r["cenario"] in cens]
    if not rows:
        print("ERRO: nenhuma linha de fase util para os cenarios pedidos", file=sys.stderr)
        return 1
    if "taxa_ofertada_rps" not in rows[0]:
        print("ERRO: summary-runs.csv sem taxa_ofertada_rps; gere de novo com scripts/consolidate.py",
              file=sys.stderr)
        return 1
    sintetico = any(r.get("tipo") == "synthetic" or r.get("run_id", "").startswith("SINT") for r in rows)

    dados = {}
    for c in cens:
        rs = [r for r in rows if r["cenario"] == c]
        if not rs:
            continue
        ofertas = {num(r["taxa_ofertada_rps"]) for r in rs}
        if len(ofertas) != 1:
            print(f"ERRO: {c} com taxas ofertadas diferentes entre repeticoes: {ofertas}", file=sys.stderr)
            return 1
        dados[c] = {
            "n": len(rs), "oferta": ofertas.pop(),
            "p95": resumo([num(r["p95_ms"]) for r in rs]),
            "p99": resumo([num(r["p99_ms"]) for r in rs]),
            "vazao": resumo([num(r["vazao_sucesso_rps"]) for r in rs]),
            "erro": resumo([num(r["erro_composto_pct"]) for r in rs]),
            "dropped": sum(int(float(r["dropped_iterations"] or 0)) for r in rs),
        }
    ordem = sorted(dados, key=lambda c: dados[c]["oferta"])
    x = list(range(len(ordem)))
    rot = [f"{c}\n{fs.num_br(dados[c]['oferta'])}" for c in ordem]

    fs.aplicar_estilo()
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=fs.cm(fs.LARGURA_CM, a.altura_cm))

    def barra(ax, xs, chave, cor, marcador, rotulo, dx=0.0):
        pts = [(xi + dx, dados[c][chave]) for xi, c in zip(xs, ordem) if dados[c][chave][0] is not None]
        if not pts:
            return
        px = [p[0] for p in pts]
        med = [p[1][0] for p in pts]
        lo = [p[1][0] - p[1][1] for p in pts]
        hi = [p[1][2] - p[1][0] for p in pts]
        ax.errorbar(px, med, yerr=[lo, hi], color=cor, marker=marcador, ms=3.5, lw=1.2,
                    capsize=2.2, elinewidth=0.8, label=rotulo, zorder=3)

    barra(a1, x, "p95", fs.COR["p95"], "o", "P95", -0.06)
    barra(a1, x, "p99", fs.COR["p99"], "s", "P99", 0.06)
    a1.set_ylabel("Latência do cliente (ms)")
    a1.set_title("(a) Latência do cliente", loc="left")
    a1.legend(loc="upper left")

    a2.plot(x, [dados[c]["oferta"] for c in ordem], color=fs.COR["oferta"], marker="o", ms=3.5,
            ls="--", lw=1.0, label="Ofertada", zorder=2)
    barra(a2, x, "vazao", fs.COR["vazao"], "s", "Vazão c/ sucesso")
    a2.set_ylabel("Requisições/s (RPS)")
    a2.set_title("(b) Oferta × vazão", loc="left")
    a2.legend(loc="upper left")
    drop = [f"{c} = {dados[c]['dropped']}" for c in ordem if dados[c]["dropped"]]
    if drop:  # canto inferior direito: nao colide com a legenda nem com a curva
        a2.text(0.98, 0.04, "dropped_iterations (soma):\n" + "; ".join(drop), transform=a2.transAxes,
                ha="right", va="bottom", fontsize=5.8, color=fs.COR["dropped"])

    med_erro = [dados[c]["erro"][0] if dados[c]["erro"][0] is not None else 0 for c in ordem]
    lo = [m - (dados[c]["erro"][1] or 0) for m, c in zip(med_erro, ordem)]
    hi = [(dados[c]["erro"][2] or 0) - m for m, c in zip(med_erro, ordem)]
    a3.bar(x, med_erro, width=0.55, color=fs.COR["erro"], alpha=0.85, zorder=2)
    a3.errorbar(x, med_erro, yerr=[lo, hi], fmt="none", ecolor="#5f4a32", elinewidth=0.8, capsize=2.2, zorder=3)
    topo = max([dados[c]["erro"][2] or 0 for c in ordem] + [0.1])
    for xi, c, m in zip(x, ordem, med_erro):
        txt = "indef." if dados[c]["erro"][0] is None else f"{fs.num_br(m, 2)}%"
        a3.text(xi, (dados[c]["erro"][2] or m) + topo * 0.05, txt, ha="center", va="bottom", fontsize=6)
    a3.set_ylim(0, topo * 1.3)
    a3.set_ylabel("Erro composto (%)")
    a3.set_title("(c) Erro composto", loc="left")

    for ax in (a1, a2, a3):
        ax.set_xticks(x)
        ax.set_xticklabels(rot)
        ax.set_xlim(-0.5, len(x) - 0.5)
        ax.set_ylim(bottom=0)
        ax.grid(axis="x", visible=False)
        ax.set_xlabel("Cenário / taxa ofertada (RPS)", fontsize=6.5, color=fs.COR["eixo"])
    a3.set_ylim(0, topo * 1.3)
    fs.formatar_eixos((a1, a2, a3))
    ns = {dados[c]["n"] for c in ordem}
    nota = (f"n = {ns.pop()} repetições válidas por cenário" if len(ns) == 1 else
            "n por cenário: " + ", ".join(f"{c}={dados[c]['n']}" for c in ordem))
    nota += " • marcador: mediana • barra: mínimo–máximo das repetições"
    fig.text(0.995, 0.005, nota, ha="right", va="bottom", fontsize=5.8, color=fs.COR["eixo"])
    fig.tight_layout(pad=0.4, w_pad=1.2, rect=(0, 0.04, 1, 0.93 if sintetico else 1))
    fs.salvar(fig, a.saida, VERSION, [a.summary_runs],
              {"cenarios": ordem, "fase": "util", "estatistica": "mediana [min-max] das repeticoes",
               "n": {c: dados[c]["n"] for c in ordem}}, sintetico)
    return 0


if __name__ == "__main__":
    sys.exit(main())
