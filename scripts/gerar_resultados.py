#!/usr/bin/env python3
"""Gera TODOS os resultados do artigo com um comando, a partir das execucoes aprovadas.

  1. consolida as execucoes VALIDA (consolidate.py)
  2. escolhe, para C4, C5 e C6 (e C7), a execucao representativa: a de Delta P95 mediano
     entre as repeticoes validas (com numero par, a mediana inferior)
  3. gera as figuras: Figura 3, Figura 4, C10 (rampa), C12, C13, C14 (e C7, se existir)
  4. gera as tabelas: Tabelas 2 e 3, Quadro 3, Tabelas A1, A2 e A3 (tabelas_artigo.py)
  5. grava results/resultados-<UTC>.md com commit, escolhas, avisos e SHA-256 de cada arquivo
  6. opcional: copia figuras, tabelas e relatorio para uma pasta do Windows (--copiar-para)

Uso: python3 scripts/gerar_resultados.py [--runs runs/campaign] [--rampa runs/pilot/RAMP-<UTC>]
                                         [--copiar-para /mnt/c/Users/<usuario>/Documents/TCC2-resultados]
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocolo as pr  # noqa: E402
from figstyle import sha256_arquivo  # noqa: E402
from run_context import ler_csv, ler_texto  # noqa: E402

VERSION = "gerar_resultados/1.0"
AQUI = os.path.dirname(os.path.abspath(__file__))
FIGURAS_PERT = [  # (cenario, tipo, arquivo)
    ("C4", "fig4", "fig04-c4-temporal.png"),
    ("C4", "cpu", "C12-cpu.png"),
    ("C5", "mem", "C13-memoria.png"),
    ("C6", "rede", "C14-rede.png"),
    ("C7", "falha", "C7-falha-api.png"),
]


def rodar(script: str, *args) -> tuple[int, str]:
    p = subprocess.run([sys.executable, os.path.join(AQUI, script), *map(str, args)], capture_output=True,
                       text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def num(v):
    return None if v in (None, "", "None") else float(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs/campaign")
    ap.add_argument("--rampa", help="pasta da rampa (padrao: a mais recente em runs/pilot)")
    ap.add_argument("--processados", default="results/processed")
    ap.add_argument("--figuras", default="results/charts")
    ap.add_argument("--slo", default=os.path.join(pr.CENARIOS_DIR, "slo.env"))
    ap.add_argument("--janela", default="10", help="janela do P95 nas series temporais (s)")
    ap.add_argument("--copiar-para", help="pasta de destino (ex.: /mnt/c/Users/<usuario>/Documents/TCC2-resultados)")
    a = ap.parse_args()
    avisos, gerados = [], []
    quando = dt.datetime.now(dt.timezone.utc)

    # 0) execucoes ainda pendentes de decisao
    pend = []
    for n in glob.glob(os.path.join(a.runs, "*", "notes.md")):
        if re.search(r"(?im)^\s*-\s*Classificacao final:\s*PENDENTE\s*$", ler_texto(n)):
            pend.append(os.path.basename(os.path.dirname(n)))
    if pend:
        avisos.append(f"{len(pend)} execucao(oes) ainda PENDENTE(S), fora dos resultados: {', '.join(sorted(pend))}")

    # 1) consolidacao
    rc, out = rodar("consolidate.py", a.runs, a.processados)
    print(f"[1/5] consolidacao: {out.splitlines()[-1] if out else rc}")
    if rc != 0:
        print(out, file=sys.stderr)
        print("Nenhuma execucao VALIDA para consolidar? Rode antes: python3 scripts/revisar_execucoes.py --aplicar",
              file=sys.stderr)
        return rc
    resumo = os.path.join(a.processados, "summary-runs.csv")
    linhas = ler_csv(resumo)
    por_cen: dict[str, dict] = {}
    for r in linhas:
        e = por_cen.setdefault(r["cenario"], {"runs": {}, "fases": set()})
        e["runs"].setdefault(r["run_id"], {})[r["fase"]] = r
        e["fases"].add(r["fase"])
    n_cen = {c: len(e["runs"]) for c, e in por_cen.items()}
    for c, n in sorted(n_cen.items()):
        if n != 3:
            avisos.append(f"{c} com {n} repeticao(oes) valida(s) (o protocolo pede 3)")

    # 2) execucao representativa por cenario com perturbacao
    escolhas = {}
    for c, e in sorted(por_cen.items()):
        if "durante" not in e["fases"]:
            continue
        cand = []
        for rid, fz in e["runs"].items():
            delta = num(next(iter(fz.values())).get("delta_p95_ms"))
            cand.append((delta if delta is not None else float("inf"), rid))
        cand.sort()
        delta, rid = cand[(len(cand) - 1) // 2]
        escolhas[c] = {"run_id": rid, "delta_p95_ms": None if delta == float("inf") else delta,
                       "candidatas": [{"run_id": r, "delta_p95_ms": None if d == float("inf") else d}
                                      for d, r in cand]}
    print("[2/5] execucoes representativas (Delta P95 mediano): "
          + (", ".join(f"{c}={v['run_id']}" for c, v in escolhas.items()) or "nenhuma"))

    # 3) figuras
    os.makedirs(a.figuras, exist_ok=True)
    falhas = []

    def fig(script, saida, *args):
        caminho = os.path.join(a.figuras, saida)
        rc, out = rodar(script, *args, "--saida", caminho)
        if rc == 0:
            gerados.append(caminho)
        else:
            falhas.append(f"{saida}: {out.splitlines()[-1] if out else rc}")

    if any("util" in e["fases"] for e in por_cen.values()):
        fig("fig_carga.py", "fig03-carga.png", resumo)
    for c, tipo, saida in FIGURAS_PERT:
        if c in escolhas:
            fig("fig_perturbacao.py", saida, os.path.join(a.runs, escolhas[c]["run_id"]), "--tipo", tipo,
                "--janela", a.janela)
        elif c != "C7":
            avisos.append(f"sem execucao valida de {c}: {saida} nao gerada")
    rampa = a.rampa or (sorted(glob.glob(os.path.join("runs", "pilot", "RAMP-*"))) or [None])[-1]
    if rampa:
        fig("fig_rampa.py", "C10-rampa.png", rampa)
    else:
        avisos.append("nenhuma rampa em runs/pilot: C10-rampa.png nao gerada")
    with open(os.path.join(a.figuras, "escolhas.json"), "w", encoding="utf-8") as fh:
        json.dump({"criterio": "Delta P95 (durante - antes) mediano entre as repeticoes validas", "escolhas": escolhas,
                   "rampa": rampa}, fh, indent=2, ensure_ascii=False)
    print(f"[3/5] figuras: {len(gerados)} geradas" + (f"; FALHAS: {falhas}" if falhas else ""))

    # 4) tabelas
    tab_dir = os.path.join(a.processados, "tabelas")
    rc, out = rodar("tabelas_artigo.py", "--resumo", resumo, "--runs", a.runs, "--slo", a.slo, "--saida", tab_dir)
    print(f"[4/5] tabelas: {out.splitlines()[0] if out else rc}")
    if rc != 0:
        falhas.append(f"tabelas: {out}")
    for li in out.splitlines():
        if li.startswith("AVISO"):
            avisos.append(li.replace("AVISO: ", ""))
    tabelas = sorted(glob.glob(os.path.join(tab_dir, "*")))

    # 5) relatorio
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    sujo = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True,
                               text=True).stdout.strip())
    versao = pr.ler_env(pr.COMMON).get("PROTOCOL_VERSION", "?")
    rel = os.path.join(os.path.dirname(os.path.normpath(a.processados)),
                       f"resultados-{quando.strftime('%Y%m%dT%H%M%SZ')}.md")
    with open(rel, "w", encoding="utf-8") as fh:
        fh.write(f"# Resultados gerados em {quando.isoformat(timespec='seconds')}\n\n")
        fh.write(f"- Script: {VERSION}\n- Commit: {commit or '?'}{' (com alteracoes locais)' if sujo else ''}\n"
                 f"- Protocolo: {versao}\n- Execucoes validas por cenario: "
                 + ", ".join(f"{c}={n}" for c, n in sorted(n_cen.items())) + "\n\n")
        fh.write("## Execucoes representativas (Delta P95 mediano)\n\n| Cenario | run_id | Delta P95 (ms) | "
                 "Candidatas |\n|---|---|---|---|\n")
        for c, v in escolhas.items():
            cands = "; ".join(f"{x['run_id']} ({x['delta_p95_ms']})" for x in v["candidatas"])
            fh.write(f"| {c} | {v['run_id']} | {v['delta_p95_ms']} | {cands} |\n")
        fh.write(f"\nRampa usada na Figura C10: {rampa or '-'}\n\n## Avisos\n\n")
        fh.write("\n".join(f"- {x}" for x in avisos + falhas) or "- nenhum")
        fh.write("\n\n## Arquivos gerados (SHA-256)\n\n| Arquivo | SHA-256 |\n|---|---|\n")
        for f in gerados + tabelas:
            if os.path.isfile(f):
                fh.write(f"| {f} | {sha256_arquivo(f)} |\n")
    print(f"[5/5] relatorio: {rel}")

    if a.copiar_para:
        os.makedirs(a.copiar_para, exist_ok=True)
        for f in gerados:
            shutil.copy2(f, a.copiar_para)
            if os.path.exists(f + ".fonte.json"):
                shutil.copy2(f + ".fonte.json", a.copiar_para)
        shutil.copy2(os.path.join(a.figuras, "escolhas.json"), a.copiar_para)
        destino_tab = os.path.join(a.copiar_para, "tabelas")
        os.makedirs(destino_tab, exist_ok=True)
        for f in tabelas:
            shutil.copy2(f, destino_tab)
        shutil.copy2(rel, a.copiar_para)
        print(f"copiado para {a.copiar_para}")

    for x in avisos + falhas:
        print(f"AVISO: {x}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
