#!/usr/bin/env python3
"""Calibracao assistida: propoe as taxas (RATE) dos cenarios a partir da rampa e, se
confirmado, grava os arquivos C*.env e as linhas "Capacidade (rampa)" e "Demandas" do
protocol-v1.md (e o joelho no notes.md da rampa).

Regras (experimental-matrix.md):
  Cap = maior degrau ESTAVEL antes do joelho (vazao com sucesso >= 95% do degrau, sem
        falhas e sem dropped_iterations). Joelho = criterio do analyze_ramp.py.
  C0 = R0 = 22,5% de Cap (meio da faixa 20-25%); C2 = 45% (40-50%); C3 = 75% (70-80%);
  cenarios com perturbacao (C4-C7) = R0. Taxas arredondadas para inteiro (minimo 1 RPS).
Avisa quando a CPU do gerador passa do limite de validade.env no degrau do joelho:
nesse caso o limite medido pode ser do NOTEBOOK, e nao do servidor.
Depois do congelamento (PROTOCOL_VERSION sem "-rascunho"), recusa gravar.

Uso: python3 scripts/calibrar_taxas.py [runs/pilot/RAMP-<UTC>] [--aplicar] [--sim]
     (sem pasta: usa a rampa mais recente de runs/pilot)
"""

from __future__ import annotations

import argparse
import glob
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocolo as pr  # noqa: E402
from analyze_ramp import analisar  # noqa: E402
from analyze_run import parse_ts  # noqa: E402
from run_context import ler_json, ler_texto, ler_vmstat  # noqa: E402

VERSION = "calibrar_taxas/1.0"
FRACOES = {"C0": (0.225, "20–25%"), "C2": (0.45, "40–50%"), "C3": (0.75, "70–80%")}


def media(pontos, a, b):
    vals = [v for t, v in pontos if a <= t < b]
    return statistics.fmean(vals) if vals else None


def analisar_rampa(d: str) -> dict:
    man = ler_json(os.path.join(d, "manifest.json"))
    t0 = parse_ts(man["k6_start_utc"])
    off = float(man.get("clock_offset_s") or 0)
    rows = analisar(d, t0, [float(s) for s in man["steps"]], float(man["step_s"]))
    vm = os.path.join(d, "notebook-vmstat.txt")
    ger = [(t - t0, v) for t, v in ler_vmstat(vm)] if os.path.exists(vm) else []
    srv = []
    pj = os.path.join(d, "server", "prom-cpu_host_pct.json")
    if os.path.exists(pj):
        res = ler_json(pj).get("data", {}).get("result", [])
        if res:
            srv = [(float(ts) - off - t0, float(v)) for ts, v in res[0]["values"] if v != "NaN"]
    for r in rows:
        r["cpu_gerador"] = media(ger, r["inicio_s"], r["fim_s"])
        r["cpu_servidor"] = media(srv, r["inicio_s"], r["fim_s"])
        r["estavel"] = (r["vazao_ok_rps"] >= 0.95 * r["degrau_rps"] and r["falhas"] == 0 and r["dropped"] == 0)
    i_joelho = next((i for i, r in enumerate(rows) if r["joelho"]), None)
    limite = rows if i_joelho is None else rows[:i_joelho]
    estaveis = [r for r in limite if r["estavel"]]
    return {"manifest": man, "rows": rows, "joelho": rows[i_joelho] if i_joelho is not None else None,
            "cap": estaveis[-1]["degrau_rps"] if estaveis else None, "tem_vmstat": bool(ger)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rampa", nargs="?")
    ap.add_argument("--aplicar", action="store_true", help="grava as taxas e o protocolo (pede confirmacao)")
    ap.add_argument("--sim", action="store_true", help="confirma sem perguntar")
    ap.add_argument("--cenarios-dir", default=pr.CENARIOS_DIR)
    ap.add_argument("--protocolo", default=pr.PROTOCOLO)
    ap.add_argument("--common", default=pr.COMMON)
    ap.add_argument("--validade", default=os.path.join(pr.CENARIOS_DIR, "validade.env"))
    a = ap.parse_args()

    d = a.rampa
    if not d:
        rampas = sorted(glob.glob(os.path.join("runs", "pilot", "RAMP-*")))
        if not rampas:
            print("nenhuma rampa em runs/pilot: rode antes  scripts/run_ramp.sh", file=sys.stderr)
            return 1
        d = rampas[-1]
    r = analisar_rampa(d)
    lim_ger = float(pr.ler_env(a.validade).get("VAL_CPU_GERADOR_MAX_PCT") or 85)
    print(f"rampa: {d}\n")
    print(f"{'degrau':>7} {'vazao_ok':>9} {'P95 ms':>8} {'falhas':>7} {'dropped':>8} {'CPU ger.':>9} "
          f"{'CPU serv.':>10}  situacao")
    for row in r["rows"]:
        f = lambda v, n=1: "-" if v is None else f"{v:.{n}f}"  # noqa: E731
        sit = "JOELHO" if row["joelho"] else ("estavel" if row["estavel"] else "instavel")
        print(f"{row['degrau_rps']:>7g} {row['vazao_ok_rps']:>9.2f} {f(row['p95_ms']):>8} {row['falhas']:>7} "
              f"{row['dropped']:>8} {f(row['cpu_gerador']):>9} {f(row['cpu_servidor']):>10}  {sit}")
    if r["cap"] is None:
        print("\nERRO: nenhum degrau estavel antes do joelho. Comece a rampa com degraus menores "
              "(ex.: scripts/run_ramp.sh 5,10,15,20,30,40 60).", file=sys.stderr)
        return 2
    avisos = []
    if r["joelho"] is None:
        avisos.append("a rampa nao atingiu o joelho: Cap pode estar subestimado (aumente os degraus)")
    elif r["joelho"]["cpu_gerador"] is not None and r["joelho"]["cpu_gerador"] > lim_ger:
        avisos.append(f"CPU do gerador {r['joelho']['cpu_gerador']:.0f}% no joelho (> {lim_ger:g}%): o limite "
                      "medido pode ser do NOTEBOOK, nao do servidor")
    if not r["tem_vmstat"]:
        avisos.append("CPU do gerador indisponivel (notebook-vmstat.txt sem horario UTC)")

    cap = r["cap"]
    envs = sorted(glob.glob(os.path.join(a.cenarios_dir, "C*.env")))
    propostas = {}
    for e in envs:
        cen = os.path.basename(e)[:-4]
        if cen in FRACOES:
            propostas[cen] = max(1, round(FRACOES[cen][0] * cap))
    if "C0" not in propostas:
        print("ERRO: C0.env nao encontrado", file=sys.stderr)
        return 1
    for e in envs:
        cen = os.path.basename(e)[:-4]
        if pr.ler_env(e).get("INTERVENTION", "none") != "none":
            propostas[cen] = propostas["C0"]
    ordem = [propostas.get(c) for c in ("C0", "C2", "C3") if c in propostas]
    if ordem != sorted(set(ordem)):
        avisos.append("taxas nao ficaram estritamente crescentes (Cap muito baixo): ajuste manualmente")

    print(f"\nCap (maior degrau estavel antes do joelho) = {cap:g} RPS"
          + (f"; joelho = {r['joelho']['degrau_rps']:g} RPS" if r["joelho"] else ""))
    print(f"\n{'cenario':<8} {'faixa':<14} {'atual':>6} {'proposta':>9}")
    for e in envs:
        cen = os.path.basename(e)[:-4]
        if cen not in propostas:
            continue
        faixa = FRACOES[cen][1] + " de Cap" if cen in FRACOES else "= R0 (C0)"
        print(f"{cen:<8} {faixa:<14} {pr.ler_env(e).get('RATE', '?'):>6} {propostas[cen]:>9}")
    for av in avisos:
        print(f"AVISO: {av}")

    if not a.aplicar:
        print("\n(nada foi gravado; para gravar:  python3 scripts/calibrar_taxas.py --aplicar)")
        return 0
    if pr.protocolo_congelado(a.common):
        print("RECUSADO: protocolo ja congelado (PROTOCOL_VERSION sem '-rascunho'). Mudancas exigem "
              "protocol-v2.md e repeticao dos cenarios afetados.", file=sys.stderr)
        return 3
    if not pr.confirmar("Gravar estas taxas nos arquivos C*.env e no protocol-v1.md?", a.sim):
        print("nada foi gravado")
        return 0
    for e in envs:
        cen = os.path.basename(e)[:-4]
        if cen in propostas:
            pr.gravar_env(e, "RATE", str(propostas[cen]))
    p95_1 = r["rows"][0]["p95_ms"]
    joelho_txt = (f"joelho em {r['joelho']['degrau_rps']:g} RPS" if r["joelho"] else "joelho nao atingido")
    pr.definir_linha_protocolo(
        a.protocolo, "Capacidade (rampa)",
        f"{joelho_txt} (P95 {p95_1} ms no 1o degrau); Cap = {cap:g} RPS (maior degrau estavel); "
        f"rampa {os.path.basename(os.path.normpath(d))}; calculado por {VERSION}")
    extras = [c for c in sorted(propostas) if c not in FRACOES]
    pr.definir_linha_protocolo(
        a.protocolo, "Demandas",
        "; ".join(f"{c} = {'R0 = ' if c == 'C0' else ''}{propostas[c]} RPS" for c in ("C0", "C2", "C3")
                  if c in propostas)
        + (f"; {', '.join(extras)} = R0" if extras else "") + " (C1 retirado do escopo)")
    notas = os.path.join(d, "notes.md")
    if os.path.exists(notas):
        txt = ler_texto(notas)
        txt = txt.replace("- Joelho escolhido (registrar em protocol-v1.md): PENDENTE",
                          f"- Joelho escolhido (registrar em protocol-v1.md): {joelho_txt}; Cap = {cap:g} RPS")
        sat = any("gerador" in av and "NOTEBOOK" in av for av in avisos)
        txt = txt.replace("- Gerador saturou (CPU do gerador alta ou dropped_iterations antes do servidor saturar)? "
                          "PENDENTE",
                          "- Gerador saturou (CPU do gerador alta ou dropped_iterations antes do servidor saturar)? "
                          + ("SIM - ver aviso do calibrar_taxas.py" if sat else "nao (CPU do gerador abaixo do "
                                                                                    "limite no joelho)"))
        with open(notas, "w", encoding="utf-8") as fh:
            fh.write(txt)
    print(f"gravado: RATE em {len(propostas)} arquivos C*.env; linhas Capacidade e Demandas em {a.protocolo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
