#!/usr/bin/env python3
"""Series temporais de UMA execucao com perturbacao (Figura 4 e Figuras C12, C13, C14).

Tipos (--tipo):
  fig4  Figura 4 do artigo (C4): P95 do cliente + CPU do servidor
  cpu   Figura C12 (C4): P95 do cliente + CPU do servidor + P95 interno da API
  mem   Figura C13 (C5): P95 do cliente + MemAvailable + swap usado (com OOM)
  rede  Figura C14 (C6): P95 do cliente x P95 interno da API + NGINX (upstream x request_time)
  falha (C7, opcional): P95 do cliente + erro composto por janela
  auto  escolhe pelo campo "intervention" do manifesto (cpu, mem, net, apifail)

Regras:
  - Faixas ANTES/DURANTE/DEPOIS = limites reais de analysis/phases.csv (horarios gravados
    pelo servidor e corrigidos pelo offset de relogio), nao os tempos nominais 240/420 s.
  - P95 por janela (--janela, padrao 10 s) pelo posto mais proximo; janela com menos de
    20 amostras fica indefinida (lacuna), nunca zero.
  - "P95 interno" = P95 das duracoes do evento request_completed (todas as requisicoes /work
    do run_id), exportado do Loki; se ausente, usa o stdout da API (api.log). Nao e a duracao
    de um unico span.
  - Recursos do servidor = series do Prometheus exportadas (rate de 30 s, passo de 5 s).
Uso: python3 scripts/fig_perturbacao.py runs/campaign/<run_id> --tipo fig4 \
        [--saida results/charts/fig04-c4-temporal.png] [--janela 10] [--altura-cm 6.5]
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import figstyle as fs  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from run_context import Execucao, janelas_p95  # noqa: E402

VERSION = "fig_perturbacao/1.0"
AUTO = {"cpu": "cpu", "mem": "mem", "net": "rede", "apifail": "falha"}
ALTURA = {"fig4": 6.5, "cpu": 9.0, "mem": 9.0, "rede": 7.0, "falha": 6.5}
NOME_PADRAO = {"fig4": "fig04-c4-temporal", "cpu": "C12-cpu-c4", "mem": "C13-memoria-c5",
               "rede": "C14-rede-c6", "falha": "C7-falha-api"}


def linha(ax, serie_t, serie_v, cor, rotulo=None, marcador="o"):
    ax.plot(serie_t, [float("nan") if v is None else v for v in serie_v], color=cor, lw=1.2,
            marker=marcador, ms=1.8, label=rotulo, zorder=3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--tipo", choices=["auto", "fig4", "cpu", "mem", "rede", "falha"], default="auto")
    ap.add_argument("--saida")
    ap.add_argument("--janela", type=float, default=10.0)
    ap.add_argument("--altura-cm", type=float)
    a = ap.parse_args()

    ex = Execucao(a.run_dir)
    inter = ex.manifest.get("intervention", "none")
    if inter == "none":
        print("ERRO: execucao sem intervencao (use fig_carga.py para C0-C3)", file=sys.stderr)
        return 1
    tipo = AUTO.get(inter, "falha") if a.tipo == "auto" else a.tipo
    ev = ex.eventos()
    t_ini, t_fim = ev["t"].get("stress_start"), ev["t"].get("stress_end")
    fases = [(n, x0, x1) for n, x0, x1 in ex.fases]
    J = a.janela
    cli = ex.serie_cliente(J)

    paineis = {"fig4": 2, "cpu": 3, "mem": 3, "rede": 2, "falha": 2}[tipo]
    fs.aplicar_estilo()
    fig, axs = plt.subplots(paineis, 1, sharex=True,
                            figsize=fs.cm(fs.LARGURA_CM, a.altura_cm or ALTURA[tipo]))
    notas = []

    # Painel 1: sempre o P95 do cliente (k6, respostas corretas)
    ax = axs[0]
    linha(ax, cli["t"], cli["p95"], fs.COR["p95"], "P95 cliente (k6)")
    ax.set_ylabel("P95 cliente\n(ms)")

    if tipo in ("fig4", "cpu"):
        cpu = ex.prom("cpu_host_pct")
        linha(axs[1], [t for t, _ in cpu], [v for _, v in cpu], fs.COR["cpu"], marcador=None)
        axs[1].set_ylabel("CPU do\nservidor (%)")
        axs[1].set_ylim(0, 105)
        if not cpu:
            notas.append("CPU do servidor: sem amostras exportadas")
    if tipo == "cpu":
        internos, fonte = ex.duracoes_internas()
        s = janelas_p95(internos, 0.0, ex.fim_rel, J)
        linha(axs[2], s["t"], s["p95"], fs.COR["interno"])
        axs[2].set_ylabel("P95 interno\nda API (ms)")
        notas.append(f"P95 interno: {fonte}")
    if tipo == "mem":
        mem = ex.prom("mem_available_bytes")
        linha(axs[1], [t for t, _ in mem], [v / 2**30 for _, v in mem], fs.COR["mem"], marcador=None)
        axs[1].axhline(2.0, color=fs.COR["limite"], ls=":", lw=0.9)
        axs[1].text(0.995, 2.0, "limite de segurança: 2 GiB", transform=axs[1].get_yaxis_transform(),
                    ha="right", va="bottom", fontsize=6, color=fs.COR["limite"])
        axs[1].set_ylabel("MemAvailable\n(GiB)")
        swap = ex.prom("swap_used_bytes")
        linha(axs[2], [t for t, _ in swap], [v / 2**30 for _, v in swap], fs.COR["swap"], marcador=None)
        axs[2].set_ylabel("Swap usado\n(GiB)")
        topo = max([v / 2**30 for _, v in swap] + [0.05])
        axs[2].set_ylim(0, topo * 1.6)
        oom = ex.oom()
        for t, _txt in oom["kernel"]:
            if t is not None:
                for x in axs:
                    x.axvline(t, color=fs.COR["limite"], lw=1.0)
        n_k = len(oom["kernel"])
        mortos = ", ".join(oom["conteineres"]) or "nenhum"
        axs[2].text(0.01, 0.92, f"OOM no kernel: {n_k} evento(s) • contêineres com OOMKilled: {mortos}",
                    transform=axs[2].transAxes, ha="left", va="top", fontsize=6,
                    color=fs.COR["limite"] if (n_k or oom["conteineres"]) else fs.COR["eixo"])
    if tipo == "rede":
        internos, fonte = ex.duracoes_internas()
        s = janelas_p95(internos, 0.0, ex.fim_rel, J)
        linha(ax, s["t"], s["p95"], fs.COR["interno"], "P95 interno (API)", "s")
        ax.set_ylabel("Latência\nP95 (ms)")
        ax.legend(loc="upper left", bbox_to_anchor=(0.0, 0.88))
        ngx = ex.nginx()
        up = janelas_p95([(t, u) for t, _r, u, _s in ngx if u is not None], 0.0, ex.fim_rel, J)
        rt = janelas_p95([(t, r) for t, r, _u, _s in ngx], 0.0, ex.fim_rel, J)
        linha(axs[1], rt["t"], rt["p95"], fs.COR["p95"], "request_time (P95)")
        linha(axs[1], up["t"], up["p95"], fs.COR["cpu"], "upstream_response_time (P95)", "s")
        axs[1].set_ylabel("NGINX,\nP95 (ms)")
        axs[1].legend(loc="upper left", bbox_to_anchor=(0.0, 0.88))
        if not ngx:
            notas.append("nginx.log ausente: painel do NGINX vazio")
        notas.append(f"P95 interno: {fonte}")
        det = ev["detalhe"].get("stress_start", "")
        if det:
            notas.append(f"intervenção: {det.split(' nginx_pid')[0]}")
    if tipo == "falha":
        att, _oks, _drp = ex.k6()
        xs, ys = [], []
        t = 0.0
        while t + J <= ex.fim_rel + 1e-9:
            dentro = [f for (tt, f) in att if t <= tt < t + J]
            xs.append(t + J / 2)
            ys.append(100.0 * sum(dentro) / len(dentro) if dentro else None)
            t += J
        linha(axs[1], xs, ys, fs.COR["dropped"])
        axs[1].set_ylabel("Erro\ncomposto (%)")
        axs[1].set_ylim(0, 105)

    for i, ax in enumerate(axs):
        fs.faixas_de_fase(ax, fases, rotulos=(i == 0), eventos=(t_ini, t_fim))
        ax.set_ylim(bottom=0)
        ax.grid(axis="x", visible=False)
    if tipo == "mem":
        axs[2].set_ylim(0, max([v / 2**30 for _, v in ex.prom("swap_used_bytes")] + [0.05]) * 1.6)
    if tipo in ("fig4", "cpu", "falha"):
        axs[1].set_ylim(0, 105)
    # Espaco no topo do 1o painel para os rotulos das fases
    y0, y1 = axs[0].get_ylim()
    axs[0].set_ylim(0, y1 * 1.22)
    if tipo == "rede":
        y0, y1 = axs[1].get_ylim()
        axs[1].set_ylim(0, y1 * 1.25)
    fim = ex.fim_rel
    axs[-1].set_xlim(0, fim)
    passo = 60 if fim > 200 else 10
    axs[-1].set_xticks([x for x in range(0, int(fim) + 1, passo)])
    axs[-1].set_xlabel("Tempo desde o início da carga (s)")
    fs.formatar_eixos(axs, eixo_x=True)
    if tipo == "fig4":
        axs[0].legend().remove() if axs[0].get_legend() else None

    altura = a.altura_cm or ALTURA[tipo]
    partes = [f"run_id {ex.run_id}", f"P95 em janelas de {fs.num_br(J)} s (mín. 20 respostas)",
              f"tracejado: início/fim da intervenção (relógio do servidor; offset {fs.num_br(ex.offset, 3)} s)"]
    partes += notas
    fig.align_ylabels(axs)
    base = fs.rodape(fig, partes, altura)
    fig.tight_layout(pad=0.4, h_pad=0.5, rect=(0, base, 1, fs.topo(altura, ex.sintetica)))
    saida = a.saida or os.path.join("results", "charts", f"{NOME_PADRAO[tipo]}-{ex.cenario}-{ex.repeticao}.png")
    fs.salvar(fig, saida, VERSION, ex.lidos + [os.path.join(a.run_dir, "analysis", "phases.csv")],
              {"tipo": tipo, "run_id": ex.run_id, "janela_s": J,
               "fases": {n: [round(x0, 3), round(x1, 3)] for n, x0, x1 in fases}}, ex.sintetica)
    return 0


if __name__ == "__main__":
    sys.exit(main())
