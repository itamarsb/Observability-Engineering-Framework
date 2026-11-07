#!/usr/bin/env python3
"""Revisao automatica das execucoes: aplica os criterios de validade do protocolo
(linha "Validade" do protocol-v1.md, limites em validade.env) e propoe, para cada pasta:

  VALIDA        todos os criterios atendidos
  INVALIDA      falha tecnica (k6, analise, sonda, exportacao, intervencao, integridade)
  INCONCLUSIVA  precisa da decisao do operador (dropped_iterations, CPU do gerador alta,
                lacuna de telemetria, OOM do kernel, reinicio de conteiner, duplicata)

Sem --aplicar: so mostra a tabela e grava um relatorio em runs/campaign-logs/.
Com --aplicar (pede confirmacao): grava no notes.md de cada execucao PENDENTE o resultado de
cada dimensao e a classificacao (VALIDA/INVALIDA). INCONCLUSIVAS continuam PENDENTES, com
os motivos anotados, para o operador decidir. Classificacoes ja feitas nao sao alteradas
(use --reclassificar para refazer as que foram gravadas por este script).

Uso: python3 scripts/revisar_execucoes.py [runs/campaign] [--aplicar] [--sim] [--reclassificar]
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocolo as pr  # noqa: E402
from analyze_run import parse_ts  # noqa: E402
from run_context import Execucao, ler_csv, ler_json, ler_texto  # noqa: E402

VERSION = "revisar_execucoes/1.0"
RE_CLASSE = re.compile(r"(?im)^\s*-\s*Classificacao final:\s*(VALIDA|INVALIDA|PENDENTE)\s*$")
MARCA = "- Revisao automatica:"


def conferir_checksums(pasta: str) -> tuple[bool, str]:
    ck = os.path.join(pasta, "checksums.sha256")
    if not os.path.exists(ck):
        return False, "checksums.sha256 ausente"
    ruins = []
    for linha in ler_texto(ck).splitlines():
        if not linha.strip():
            continue
        h, rel = linha.split(None, 1)
        caminho = os.path.join(pasta, rel.strip().lstrip("*"))
        if not os.path.exists(caminho):
            ruins.append(f"{rel.strip()} ausente")
            continue
        sha = hashlib.sha256()
        with open(caminho, "rb") as fh:
            for bloco in iter(lambda: fh.read(1 << 20), b""):
                sha.update(bloco)
        if sha.hexdigest() != h:
            ruins.append(f"{rel.strip()} alterado")
    return (not ruins), ("conferido" if not ruins else "; ".join(ruins[:3]))


def avaliar(pasta: str, lim: dict) -> dict:
    """Devolve {proposta, dimensoes{carga,sonda,telemetria,intervencao,integridade}, motivos}."""
    dim = {k: [] for k in ("carga", "sonda", "telemetria", "intervencao", "integridade")}
    inval, inconc = [], []
    notas = os.path.join(pasta, "notes.md")
    txt_notas = ler_texto(notas) if os.path.exists(notas) else ""
    if "INVALIDA:" in txt_notas:
        motivo = next((li.split("INVALIDA:", 1)[1].strip() for li in txt_notas.splitlines() if "INVALIDA:" in li),
                      "falha tecnica")
        inval.append(f"run_scenario.sh: {motivo}")
    man = ler_json(os.path.join(pasta, "manifest.json"))
    if not os.path.exists(os.path.join(pasta, "analysis", "phases.csv")):
        inval.append("sem analise (analysis/phases.csv)")
        return {"proposta": "INVALIDA", "dimensoes": dim, "invalidos": inval, "inconclusivos": inconc,
                "manifest": man}
    ex = Execucao(pasta)
    fases = [f for f, _, _ in ex.fases if f != "aquecimento"]
    linhas = {r["fase"]: r for r in ler_csv(os.path.join(pasta, "analysis", "phases.csv"))}

    # --- carga ---
    k6x = man.get("k6_exit_code")
    if k6x != 0:
        inval.append(f"k6 terminou com codigo {k6x}")
        dim["carga"].append(f"k6 codigo {k6x}")
    else:
        dim["carga"].append("k6 codigo 0")
    drp = sum(int(float(linhas[f]["dropped_iterations"] or 0)) for f in fases if f in linhas)
    dim["carga"].append(f"dropped {drp}")
    if drp > float(lim.get("VAL_DROPPED_MAX") or 0):
        inconc.append(f"dropped_iterations = {drp} (verificar se foi o gerador ou o servidor)")
    ctx = ex.contexto_por_fase()
    cpu_ger = [ctx[f]["cpu_gerador_max_pct"] for f in fases if ctx.get(f, {}).get("cpu_gerador_max_pct") is not None]
    lim_ger = float(lim.get("VAL_CPU_GERADOR_MAX_PCT") or 85)
    if not cpu_ger:
        inconc.append("CPU do gerador nao verificavel (notebook-vmstat.txt sem horario UTC)")
        dim["carga"].append("CPU do gerador indisponivel")
    else:
        dim["carga"].append(f"CPU do gerador max. {max(cpu_ger):.0f}%")
        if max(cpu_ger) > lim_ger:
            inconc.append(f"CPU do gerador {max(cpu_ger):.0f}% > {lim_ger:g}% (o gerador pode ter limitado a carga)")

    # --- sonda ---
    cob_min = float(lim.get("VAL_COBERTURA_SONDA_MIN_PCT") or 100)
    cobs = [(f, linhas[f]["cobertura_pct"]) for f in fases if f in linhas]
    ruins = [f"{f}={c or 'sem amostras'}" for f, c in cobs if c in ("", "None") or float(c) < cob_min]
    if ruins:
        inval.append(f"cobertura da sonda abaixo de {cob_min:g}% ({', '.join(ruins)})")
        dim["sonda"].append("cobertura incompleta: " + ", ".join(ruins))
    else:
        dim["sonda"].append(f"cobertura {cob_min:g}% em {', '.join(fases)}")

    # --- telemetria ---
    rep = os.path.join(pasta, "server", "export-report.json")
    if not os.path.exists(rep):
        inval.append("export-report.json ausente")
        dim["telemetria"].append("exportacao ausente")
    else:
        itens = ler_json(rep).get("items", {})
        erros = [k for k, v in itens.items() if isinstance(v, dict) and ("error" in v or v.get("rc") not in (None, 0))]
        if erros:
            inval.append(f"exportacao com erro em {', '.join(erros[:4])}")
            dim["telemetria"].append("exportacao com erro")
        else:
            dim["telemetria"].append("exportacao sem erro")
    lacunas = [n for n in ("cpu_host_pct", "mem_available_bytes") if not ex.prom(n)]
    if not ex.duracoes_internas()[0]:
        lacunas.append("logs request_completed")
    if lacunas:
        inconc.append(f"lacuna de telemetria: {', '.join(lacunas)} (pode ser resultado; avaliar)")
        dim["telemetria"].append("lacuna: " + ", ".join(lacunas))
    estado = os.path.join(pasta, "server", "containers-state.json")
    if os.path.exists(estado):
        t_ini_srv = ex.t0 + ex.offset
        reinic, oom = [], []
        for c in ler_json(estado):
            if c.get("oom_killed"):
                oom.append(c.get("service") or c.get("name"))
            try:
                ini = parse_ts(c.get("started_at") or "")
            except ValueError:
                continue
            esperado = man.get("intervention") == "apifail" and c.get("service") == "api"
            if ini > t_ini_srv and not esperado:
                reinic.append(c.get("service") or c.get("name"))
        if oom:
            inval.append(f"conteiner com OOMKilled: {', '.join(oom)}")
        if len(reinic) > int(float(lim.get("VAL_REINICIOS_MAX") or 0)):
            inconc.append(f"conteiner reiniciado durante a execucao: {', '.join(reinic)}")
        dim["telemetria"].append(f"OOMKilled: {', '.join(oom) or 'nenhum'}; reinicios: {', '.join(reinic) or 'nenhum'}")
    else:
        inconc.append("containers-state.json ausente")
    oom_k = sum(ctx[f]["oom_kernel"] for f in fases if f in ctx)
    if oom_k:
        inconc.append(f"{oom_k} evento(s) de OOM no kernel durante a execucao")

    # --- intervencao ---
    if man.get("intervention", "none") != "none":
        ev = ex.eventos()["t"]
        if "stress_start" not in ev or "stress_end" not in ev:
            inval.append("intervencao sem inicio/fim registrados pelo servidor")
            dim["intervencao"].append("eventos ausentes")
        elif man.get("intervention_rc") not in (0, None):
            inval.append(f"intervencao terminou com codigo {man.get('intervention_rc')}")
            dim["intervencao"].append(f"codigo {man.get('intervention_rc')}")
        else:
            dim["intervencao"].append(f"{man['intervention']}: inicio e fim registrados, codigo 0, "
                                      f"{ev['stress_end'] - ev['stress_start']:.0f} s")
    else:
        dim["intervencao"].append("nao se aplica")

    # --- integridade ---
    ok, msg = conferir_checksums(pasta)
    dim["integridade"].append(f"checksums {msg}")
    if not ok:
        inval.append(f"integridade: {msg}")

    proposta = "INVALIDA" if inval else ("INCONCLUSIVA" if inconc else "VALIDA")
    return {"proposta": proposta, "dimensoes": dim, "invalidos": inval, "inconclusivos": inconc, "manifest": man}


def classe_atual(pasta: str) -> str:
    p = os.path.join(pasta, "notes.md")
    if not os.path.exists(p):
        return "SEM NOTES"
    st = RE_CLASSE.findall(ler_texto(p))
    return st[0].upper() if len(st) == 1 else "AMBIGUA"


def gravar_notas(pasta: str, r: dict, quando: str) -> None:
    p = os.path.join(pasta, "notes.md")
    txt = ler_texto(p) if os.path.exists(p) else f"# Notas da execucao {r['manifest']['run_id']}\n" \
                                                   "- Classificacao final: PENDENTE\n"
    d = r["dimensoes"]
    trocas = {
        "- Validade da carga": "; ".join(d["carga"]),
        "- Validade da sonda": "; ".join(d["sonda"]),
        "- Validade da telemetria": "; ".join(d["telemetria"]),
        "- Intervencao aplicada como planejado?": "; ".join(d["intervencao"]),
    }
    saida = []
    for li in txt.splitlines():
        if li.startswith(MARCA) or li.startswith("  - motivo:"):
            continue  # remove a revisao automatica anterior (com --reclassificar)
        for pref, val in trocas.items():
            if li.startswith(pref) and ":" in li:
                li = f"{li.split(':', 1)[0]}: {val}"  # o rotulo do modelo nao tem ':'; o valor vem depois
        if RE_CLASSE.match(li) and r["proposta"] in ("VALIDA", "INVALIDA"):
            li = f"- Classificacao final: {r['proposta']}"
        saida.append(li)
    saida.append(f"{MARCA} {VERSION} em {quando}: {r['proposta']}; integridade: {'; '.join(d['integridade'])}")
    for m in r["invalidos"] + r["inconclusivos"]:
        saida.append(f"  - motivo: {m}")
    if r["proposta"] == "INCONCLUSIVA":
        saida.append("  - motivo: DECISAO DO OPERADOR - avaliar os motivos acima, trocar PENDENTE por VALIDA ou "
                     "INVALIDA e registrar a justificativa")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("\n".join(saida) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="?", default="runs/campaign")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--reclassificar", action="store_true",
                    help="refaz tambem as execucoes ja classificadas por este script")
    ap.add_argument("--validade", default=os.path.join(pr.CENARIOS_DIR, "validade.env"))
    a = ap.parse_args()
    lim = pr.ler_env(a.validade)
    pastas = sorted(p for p in glob.glob(os.path.join(a.runs, "*")) if os.path.isdir(p))
    sem_manifest = [os.path.basename(p) for p in pastas if not os.path.exists(os.path.join(p, "manifest.json"))]
    pastas = [p for p in pastas if os.path.exists(os.path.join(p, "manifest.json"))]
    if not pastas:
        print(f"nenhuma execucao em {a.runs}", file=sys.stderr)
        return 1
    res = []
    for p in pastas:
        r = avaliar(p, lim)
        r["pasta"], r["atual"] = p, classe_atual(p)
        r["revisado_por_script"] = MARCA in (ler_texto(os.path.join(p, "notes.md"))
                                             if os.path.exists(os.path.join(p, "notes.md")) else "")
        res.append(r)
    # duplicatas: mais de uma VALIDA (atual ou proposta) para o mesmo cenario/repeticao
    vistos: dict = {}
    for r in sorted(res, key=lambda x: x["manifest"].get("k6_start_utc", "")):
        chave = (r["manifest"].get("scenario"), r["manifest"].get("repetition"))
        valida = r["atual"] == "VALIDA" or (r["atual"] == "PENDENTE" and r["proposta"] == "VALIDA")
        if valida:
            if chave in vistos:
                r["inconclusivos"].append(f"duplicata de {os.path.basename(vistos[chave])} (mesmo cenario e repeticao)")
                if r["proposta"] == "VALIDA":
                    r["proposta"] = "INCONCLUSIVA"
            else:
                vistos[chave] = r["pasta"]

    quando = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    print(f"{'execucao':<9} {'pasta':<38} {'atual':<10} {'proposta':<13} motivos")
    for r in res:
        m = r["manifest"]
        mot = "; ".join(r["invalidos"] + r["inconclusivos"]) or "-"
        print(f"{m.get('scenario')}-{m.get('repetition'):<6} {os.path.basename(r['pasta']):<38} {r['atual']:<10} "
              f"{r['proposta']:<13} {mot[:110]}")
    if sem_manifest:
        print(f"\npastas sem manifest.json (abortadas antes de iniciar; ignoradas): {', '.join(sem_manifest)}")
    tot = {k: sum(1 for r in res if r["proposta"] == k) for k in ("VALIDA", "INVALIDA", "INCONCLUSIVA")}
    print(f"\npropostas: {tot['VALIDA']} VALIDA, {tot['INVALIDA']} INVALIDA, {tot['INCONCLUSIVA']} INCONCLUSIVA")

    logs = os.path.join(os.path.dirname(os.path.normpath(a.runs)), "campaign-logs")
    os.makedirs(logs, exist_ok=True)
    rel = os.path.join(logs, f"revisao-{quando.replace(':', '').replace('+0000', 'Z')}.md")
    with open(rel, "w", encoding="utf-8") as fh:
        fh.write(f"# Revisao automatica ({VERSION}, {quando})\n\nLimites: {lim}\n\n"
                 "| Execucao | Pasta | Atual | Proposta | Motivos |\n|---|---|---|---|---|\n")
        for r in res:
            m = r["manifest"]
            fh.write(f"| {m.get('scenario')}-{m.get('repetition')} | {os.path.basename(r['pasta'])} | {r['atual']} | "
                     f"{r['proposta']} | {'; '.join(r['invalidos'] + r['inconclusivos']) or '-'} |\n")
    print(f"relatorio: {rel}")

    if not a.aplicar:
        print("(nada foi gravado nos notes.md; para gravar:  python3 scripts/revisar_execucoes.py --aplicar)")
        return 0
    alvo = [r for r in res if r["atual"] == "PENDENTE" or (a.reclassificar and r["revisado_por_script"])]
    if not alvo:
        print("nenhuma execucao pendente para gravar")
        return 0
    if not pr.confirmar(f"Gravar a revisao em {len(alvo)} notes.md (INCONCLUSIVAS continuam PENDENTES)?", a.sim):
        print("nada foi gravado")
        return 0
    for r in alvo:
        gravar_notas(r["pasta"], r, quando)
    pend = [r for r in alvo if r["proposta"] == "INCONCLUSIVA"]
    print(f"gravado em {len(alvo)} execucoes. Pendentes de decisao do operador: {len(pend)}")
    for r in pend:
        print(f"  nano {os.path.join(r['pasta'], 'notes.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
