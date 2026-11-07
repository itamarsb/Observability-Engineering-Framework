#!/usr/bin/env python3
"""Tabelas do artigo e dos apendices a partir das execucoes reais (prontas para colar).

Gera, em --saida:
  tabela2-carga            Tabela 2: C0-C3, mediana [min-max] de P95/P99, erro e vazao
  tabela3-perturbacoes     Tabela 3: P95 antes/durante/depois + indicio complementar (C4-C6, C7)
  quadro3-sli-slo          Quadro 3: conformidade SLI x SLO nas execucoes validas
  apendiceA1-execucoes     Tabela A1: indicadores por execucao (fase avaliada)
  apendiceA2-auditoria     Tabela A2: TODAS as execucoes da pasta, inclusive invalidas/pendentes
  apendiceA3-sli-slo       Tabela A3: SLI x SLO por execucao (detalhe do Quadro 3)
cada uma em .csv, mais tabelas-artigo.docx (todas, formatadas), tabelas-artigo.md e
tabelas-artigo.fonte.json (entradas com SHA-256).

Regras:
  - Somente execucoes aprovadas (summary-runs.csv de consolidate.py) entram nas Tabelas 2, 3,
    no Quadro 3 e nas Tabelas A1/A3. A Tabela A2 lista tudo o que existe na pasta.
  - Mediana e [minimo-maximo] das repeticoes; percentis nunca sao promediados.
  - Valor ausente = "indef." (nunca zero). Metas vazias em slo.env = Quadro 3 sem veredito.
  - Dados sinteticos: arquivos com prefixo SINTETICO_ e aviso em vermelho no DOCX.
Requer python-docx para o .docx (no WSL: pip install python-docx); sem ele, gera CSV e MD.
Uso: python3 scripts/tabelas_artigo.py --resumo results/processed/summary-runs.csv \
        --runs runs/campaign [--slo experiments/scenarios/slo.env] [--saida results/processed/tabelas]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import hashlib
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_context import Execucao, ler_csv, ler_json, ler_linhas, ler_texto  # noqa: E402

VERSION = "tabelas_artigo/1.0"
AVISO_SINT = "DADOS SINTÉTICOS — TESTE DO PIPELINE — NÃO É EVIDÊNCIA"
FONTE = "Fonte: Autoria própria ({ano})."
FASE_TXT = {"util": "útil", "antes": "antes", "durante": "durante", "depois": "depois"}
NOME_INT = {"cpu": "CPU", "mem": "RAM", "net": "rede", "apifail": "falha da API"}


# ---------------- utilitarios ----------------
def num(v):
    return None if v in (None, "", "None") else float(v)


def br(v, casas=1):
    return "indef." if v is None else f"{v:.{casas}f}".replace(".", ",")


def mmm(vals):
    vals = [v for v in vals if v is not None]
    return (statistics.median(vals), min(vals), max(vals)) if vals else (None, None, None)


def faixa(t, casas=1):
    med, lo, hi = t
    if med is None:
        return "indef."
    if lo == hi:
        return br(med, casas)
    return f"{br(med, casas)} [{br(lo, casas)}–{br(hi, casas)}]"


def ler_env(caminho):
    out = {}
    if caminho and os.path.exists(caminho):
        for linha in ler_linhas(caminho):
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    return out


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def classificacao(pasta):
    p = os.path.join(pasta, "notes.md")
    if not os.path.exists(p):
        return "SEM NOTES"
    txt = ler_texto(p)
    st = re.findall(r"(?im)^\s*-\s*Classificacao final:\s*(VALIDA|INVALIDA|PENDENTE)\s*$", txt)
    auto = "INVALIDA:" in txt
    base = st[0] if len(st) == 1 else "AMBIGUA"
    if auto:
        return "INVALIDA (auto)" if base != "VALIDA" else "CONFLITO"
    return base


class Tabela:
    def __init__(self, chave, titulo, cab, linhas, tipo="Tabela", nota=None):
        self.chave, self.titulo, self.cab, self.linhas, self.tipo, self.nota = chave, titulo, cab, linhas, tipo, nota


# ---------------- construcao das tabelas ----------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resumo", default="results/processed/summary-runs.csv")
    ap.add_argument("--runs", default="runs/campaign")
    ap.add_argument("--slo", default="experiments/scenarios/slo.env")
    ap.add_argument("--saida", default="results/processed/tabelas")
    ap.add_argument("--ano", default=str(dt.date.today().year))
    a = ap.parse_args()

    slo = ler_env(a.slo)
    fase_carga = slo.get("SLO_FASE_CARGA", "util")
    fase_pert = slo.get("SLO_FASE_PERTURBACAO", "durante")
    resumo = list(ler_csv(a.resumo))
    if not resumo:
        print("ERRO: summary-runs.csv vazio", file=sys.stderr)
        return 1
    entradas = [a.resumo] + ([a.slo] if os.path.exists(a.slo) else [])
    sintetico = any(r.get("tipo") == "synthetic" or r.get("run_id", "").startswith("SINT") for r in resumo)

    # agrupa por execucao
    por_run: dict[str, dict] = {}
    for r in resumo:
        e = por_run.setdefault(r["run_id"], {"cenario": r["cenario"], "rep": r["repeticao"], "fases": {},
                                             "oferta": num(r.get("taxa_ofertada_rps"))})
        e["fases"][r["fase"]] = r
    for rid, e in por_run.items():
        e["tipo_cen"] = "carga" if "util" in e["fases"] else "perturbacao"
        e["fase_aval"] = fase_carga if e["tipo_cen"] == "carga" else fase_pert
        pasta = os.path.join(a.runs, rid)
        e["pasta"] = pasta if os.path.isdir(pasta) else None
        e["ctx"], e["intervencao"] = None, None
        if e["pasta"]:
            ex = Execucao(pasta)
            e["intervencao"] = ex.manifest.get("intervention")
            if e["tipo_cen"] == "perturbacao":
                e["ctx"] = ex.contexto_por_fase()
                entradas += ex.lidos
    cenarios = sorted({e["cenario"] for e in por_run.values()})
    reps = lambda c: [e for e in por_run.values() if e["cenario"] == c]  # noqa: E731
    tabelas = []

    # ---- Tabela 2 ----
    linhas = []
    carga = [c for c in cenarios if reps(c)[0]["tipo_cen"] == "carga"]
    carga.sort(key=lambda c: reps(c)[0]["oferta"] or 0)
    csv2 = []
    for c in carga:
        rs = reps(c)
        f = [x["fases"]["util"] for x in rs]
        p95, p99 = mmm([num(x["p95_ms"]) for x in f]), mmm([num(x["p99_ms"]) for x in f])
        err, vaz = mmm([num(x["erro_composto_pct"]) for x in f]), mmm([num(x["vazao_sucesso_rps"]) for x in f])
        drp = sum(int(float(x["dropped_iterations"] or 0)) for x in f)
        linhas.append([c, br(rs[0]["oferta"], 0), faixa(p95), faixa(p99), br(err[0], 2), br(vaz[0], 1)])
        csv2.append({"cenario": c, "n": len(rs), "oferta_rps": rs[0]["oferta"],
                     **{f"{k}_{s}": v for k, t in (("p95_ms", p95), ("p99_ms", p99), ("erro_pct", err),
                                                     ("vazao_rps", vaz))
                        for s, v in zip(("mediana", "min", "max"), t)}, "dropped_soma": drp})
    ns = sorted({len(reps(c)) for c in carga})
    tabelas.append(Tabela("tabela2-carga", f"Tabela 2 - Carga e SLIs: mediana [mín.–máx.] em "
                          f"{'/'.join(map(str, ns))} execuções", ["Cen.", "Oferta (RPS)", "P95 (ms)", "P99 (ms)",
                                                                  "Erro (%)", "Vazão (RPS)"], linhas,
                          nota="Erro e vazão: mediana das repetições. Fase útil de 180 s; percentis pelo "
                               "método do posto mais próximo."))

    # ---- Tabela 3 ----
    linhas, csv3 = [], []
    pert = [c for c in cenarios if reps(c)[0]["tipo_cen"] == "perturbacao"]
    for c in pert:
        rs = reps(c)
        p = {fz: mmm([num(x["fases"][fz]["p95_ms"]) for x in rs if fz in x["fases"]])
             for fz in ("antes", "durante", "depois")}
        inter = rs[0]["intervencao"] or "?"
        ctxs = [x["ctx"] for x in rs if x["ctx"]]

        def med(fase, chave):
            vals = [cx[fase][chave] for cx in ctxs if fase in cx and cx[fase].get(chave) is not None]
            return statistics.median(vals) if vals else None
        if inter == "cpu":
            ind = (f"CPU servidor (média): {br(med('antes', 'cpu_servidor_media_pct'), 0)}% → "
                   f"{br(med('durante', 'cpu_servidor_media_pct'), 0)}%; P95 interno: "
                   f"{br(med('antes', 'p95_interno_ms'))} → {br(med('durante', 'p95_interno_ms'))} ms")
        elif inter == "mem":
            oom = sum(cx[fz]["oom_kernel"] for cx in ctxs for fz in ("antes", "durante", "depois") if fz in cx)
            mortos = sorted({m for cx in ctxs for m in cx.get("_oom_conteineres", [])})
            ind = (f"MemAvailable (mín.): {br(med('antes', 'mem_disponivel_min_gib'))} → "
                   f"{br(med('durante', 'mem_disponivel_min_gib'))} GiB; swap máx.: "
                   f"{br(med('durante', 'swap_max_gib'), 2)} GiB; OOM: {oom}"
                   + (f" ({', '.join(mortos)})" if mortos else ""))
        elif inter == "net":
            ind = (f"P95 interno: {br(med('antes', 'p95_interno_ms'))} → {br(med('durante', 'p95_interno_ms'))} ms; "
                   f"upstream NGINX P95: {br(med('antes', 'p95_upstream_nginx_ms'))} → "
                   f"{br(med('durante', 'p95_upstream_nginx_ms'))} ms")
        else:
            err = mmm([num(x["fases"]["durante"]["erro_composto_pct"]) for x in rs if "durante" in x["fases"]])
            ind = f"erro composto durante: {br(err[0], 2)}%"
        linhas.append([f"{c} / {NOME_INT.get(inter, inter)}",
                       f"{br(p['antes'][0])} / {br(p['durante'][0])} / {br(p['depois'][0])}", ind])
        csv3.append({"cenario": c, "intervencao": inter, "n": len(rs),
                     **{f"p95_{fz}_{s}": v for fz in p for s, v in zip(("mediana", "min", "max"), p[fz])},
                     "indicio": ind})
    tabelas.append(Tabela("tabela3-perturbacoes", "Tabela 3 - Efeito das perturbações sobre P95 e "
                          "métricas auxiliares (mediana das repetições)",
                          ["Cen.", "P95 antes / durante / depois (ms)", "Indício complementar"], linhas,
                          nota="P95 do cliente (k6). Indícios: séries do Prometheus, evento request_completed "
                               "(Loki) e log do NGINX na mesma janela; descritivos, não causais."))

    # ---- Quadro 3 e Tabela A3 ----
    def meta(k):
        v = slo.get(k, "")
        return float(v) if v not in ("", None) else None
    m95, m99 = meta("SLO_P95_MS"), meta("SLO_P99_MS")
    merr, mfr = meta("SLO_ERRO_MAX_PCT") or 1.0, meta("SLO_VAZAO_MIN_FRACAO") or 0.95
    msd, mcob = meta("SLO_SONDA_MIN_PCT") or 99.0, meta("SLO_COBERTURA_PCT") or 100.0
    crit = ["P95 cliente", "P99 cliente", "Erro composto", "Vazão / demanda", "Sonda independente"]
    por_exec, linhasA3 = [], []
    ordem_runs = sorted(por_run.items(), key=lambda kv: (kv[1]["cenario"], kv[1]["rep"]))
    for rid, e in ordem_runs:
        f = e["fases"].get(e["fase_aval"])
        if f is None:
            continue
        p95, p99, err = num(f["p95_ms"]), num(f["p99_ms"]), num(f["erro_composto_pct"])
        vaz, drp = num(f["vazao_sucesso_rps"]), int(float(f["dropped_iterations"] or 0))
        cob, disp = num(f["cobertura_pct"]), num(f["disponibilidade_pct"])

        def le(v, m):
            return None if v is None or m is None else v <= m
        r = {
            "P95 cliente": le(p95, m95), "P99 cliente": le(p99, m99), "Erro composto": le(err, merr),
            "Vazão / demanda": None if vaz is None or not e["oferta"] else (vaz >= mfr * e["oferta"] and drp == 0),
            "Sonda independente": None if cob is None or cob < mcob or disp is None else disp >= msd,
        }
        vals = list(r.values())
        r["Conjunto dos critérios"] = False if False in vals else (None if None in vals else True)
        por_exec.append(r)
        s = lambda b: "—" if b is None else ("atende" if b else "NÃO")  # noqa: E731
        linhasA3.append([f"{e['cenario']}-{e['rep']}", FASE_TXT.get(e["fase_aval"], e["fase_aval"]),
                         br(p95), br(p99), br(err, 2),
                         f"{br(vaz)}/{br(e['oferta'], 0)}", f"{br(disp)}% ({br(cob, 0)}%)",
                         s(r["Conjunto dos critérios"])])
    metas_txt = {
        "P95 cliente": f"≤ {br(m95, 0)} ms" if m95 is not None else "meta não congelada",
        "P99 cliente": f"≤ {br(m99, 0)} ms" if m99 is not None else "meta não congelada",
        "Erro composto": f"≤ {br(merr, 0)}%",
        "Vazão / demanda": f"≥ {br(mfr * 100, 0)}%, dropped = 0",
        "Sonda independente": f"≥ {br(msd, 0)}% corretas; {br(mcob, 0)}% cobertura",
        "Conjunto dos critérios": "Todos acima simultaneamente",
    }
    linhas = []
    N = len(por_exec)
    for k in crit + ["Conjunto dos critérios"]:
        ok = sum(1 for r in por_exec if r[k] is True)
        ind = sum(1 for r in por_exec if r[k] is None)
        txt = f"{ok}/{N}" + (f" (indef.: {ind})" if ind else "")
        if k in ("P95 cliente", "P99 cliente") and metas_txt[k] == "meta não congelada":
            txt = "—"
        linhas.append([k, metas_txt[k], txt])
    tabelas.append(Tabela("quadro3-sli-slo", f"Quadro 3 - Critérios SLI × SLO e atendimentos ({N} execuções)",
                          ["Indicador", "Meta do protocolo", "Conformidade"], linhas, tipo="Quadro",
                          nota=f"Fase avaliada: {FASE_TXT.get(fase_carga, fase_carga)} (C0–C3) e "
                               f"{FASE_TXT.get(fase_pert, fase_pert)} (C4–C7). "
                               "indef. = sem amostras válidas ou cobertura da sonda incompleta."))

    # ---- Tabela A1 ----
    linhas = []
    for rid, e in ordem_runs:
        f = e["fases"].get(e["fase_aval"])
        if f is None:
            continue
        linhas.append([f"{e['cenario']}-{e['rep']}", e["cenario"], FASE_TXT.get(e["fase_aval"], e["fase_aval"]),
                       f["respostas_corretas"], br(num(f["p95_ms"])), br(num(f["p99_ms"])),
                       br(num(f["erro_composto_pct"]), 2),
                       br(num(f["vazao_sucesso_rps"])), f["dropped_iterations"]])
    tabelas.append(Tabela("apendiceA1-execucoes", "Tabela A1 - Indicadores por execução válida (fase avaliada)",
                          ["Run", "Cenário", "Fase", "N", "P95 ms", "P99 ms", "Erro %", "Vazão RPS", "Dropped"],
                          linhas, nota="N = respostas corretas na fase. C4–C7: fase durante."))
    tabelas.append(Tabela("apendiceA3-sli-slo", "Tabela A3 - SLI × SLO por execução",
                          ["Run", "Fase", "P95", "P99", "Erro %", "Vazão/oferta", "Sonda (cobertura)",
                           "Conjunto"], linhasA3, nota="— = indefinido (sem amostras ou meta não congelada)."))

    # ---- Tabela A2 (todas as execucoes da pasta) ----
    linhas, csvA2 = [], []
    pastas = sorted(p for p in glob.glob(os.path.join(a.runs, "*")) if os.path.isdir(p)
                    and os.path.exists(os.path.join(p, "manifest.json")))
    regs = []
    for p in pastas:
        m = ler_json(os.path.join(p, "manifest.json"))
        sj = os.path.join(p, "analysis", "summary.json")
        ph = os.path.join(p, "analysis", "phases.csv")
        n_http = ler_json(sj).get("k6_total_tentativas") if os.path.exists(sj) else None
        drp = sond_ok = sond_n = None
        if os.path.exists(ph):
            fz = list(ler_csv(ph))
            drp = sum(int(float(x["dropped_iterations"] or 0)) for x in fz)
            sond_ok = sum(int(x["sondas_corretas"] or 0) for x in fz)
            sond_n = sum(int(x["sondas_previstas"] or 0) for x in fz)
        ck = os.path.join(p, "checksums.sha256")
        h = sha256(ck) if os.path.exists(ck) else None
        regs.append((m.get("k6_start_utc", ""), m, n_http, drp, sond_ok, sond_n, classificacao(p), h))
    for ini, m, n_http, drp, sok, sn, st, h in sorted(regs, key=lambda x: x[0]):
        ini_txt = ini[:19].replace("T", " ") + "Z" if ini else "indef."
        linhas.append([f"{m.get('scenario')}-{m.get('repetition')}", ini_txt, "indef." if n_http is None else n_http,
                       "indef." if drp is None else drp, "indef." if sn is None else f"{sok}/{sn}", st,
                       (h[:16] + "…") if h else "sem checksums"])
        csvA2.append({"id_planejado": f"{m.get('scenario')}-{m.get('repetition')}", "run_id": m.get("run_id"),
                      "inicio_utc": ini, "n_http": n_http, "dropped": drp, "sonda_ok": sok, "sonda_n": sn,
                      "estado": st, "sha256_checksums": h})
    tabelas.append(Tabela("apendiceA2-auditoria", "Tabela A2 - Auditoria de validade e integridade das execuções",
                          ["ID planejado", "Início UTC", "N HTTP", "Dropped", "Sonda OK/N", "Estado",
                           "Manifesto/hash"], linhas,
                          nota="Todas as execuções da pasta, inclusive inválidas e pendentes. Hash = SHA-256 do "
                               "arquivo checksums.sha256 (16 primeiros dígitos; completo no CSV)."))

    # ---------------- gravacao ----------------
    os.makedirs(a.saida, exist_ok=True)
    pre = "SINTETICO_" if sintetico else ""
    extras = {"tabela2-carga": csv2, "tabela3-perturbacoes": csv3, "apendiceA2-auditoria": csvA2}
    for t in tabelas:
        destino = os.path.join(a.saida, f"{pre}{t.chave}.csv")
        with open(destino, "w", newline="", encoding="utf-8") as fh:
            if t.chave in extras and extras[t.chave]:
                w = csv.DictWriter(fh, fieldnames=list(extras[t.chave][0].keys()))
                w.writeheader()
                w.writerows(extras[t.chave])
            else:
                w = csv.writer(fh)
                w.writerow(t.cab)
                w.writerows(t.linhas)
    md = [f"> **{AVISO_SINT}**\n" if sintetico else ""]
    for t in tabelas:
        md.append(f"**{t.titulo}**\n")
        md.append("| " + " | ".join(t.cab) + " |")
        md.append("|" + "---|" * len(t.cab))
        for li in t.linhas:
            md.append("| " + " | ".join(str(x) for x in li) + " |")
        md.append(f"\n{FONTE.format(ano=a.ano)}" + (f" {t.nota}" if t.nota else "") + "\n")
    with open(os.path.join(a.saida, f"{pre}tabelas-artigo.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))
    docx_ok = gerar_docx(tabelas, os.path.join(a.saida, f"{pre}tabelas-artigo.docx"), sintetico, a.ano)
    fonte = {"script": VERSION, "gerado_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "dados_sinteticos": sintetico, "slo": slo, "execucoes_validas": len(por_run),
             "entradas": [{"arquivo": e, "sha256": sha256(e)} for e in sorted(set(entradas)) if os.path.isfile(e)]}
    with open(os.path.join(a.saida, f"{pre}tabelas-artigo.fonte.json"), "w", encoding="utf-8") as fh:
        json.dump(fonte, fh, indent=2, ensure_ascii=False)
    print(f"{len(tabelas)} tabelas em {a.saida} (CSV, MD{', DOCX' if docx_ok else ''})"
          + ("  [SINTETICO]" if sintetico else ""))
    if m95 is None or m99 is None:
        print("AVISO: SLO_P95_MS/SLO_P99_MS vazios em slo.env - Quadro 3 sem veredito de latencia")
    return 0


# ---------------- DOCX ----------------
def gerar_docx(tabelas, caminho, sintetico, ano) -> bool:
    try:
        from docx import Document
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Cm, Pt, RGBColor
    except ImportError:
        print("AVISO: python-docx ausente (pip install python-docx); DOCX nao gerado")
        return False

    def borda(cell, **lados):
        tcPr = cell._tc.get_or_add_tcPr()
        b = tcPr.find(qn("w:tcBorders"))
        if b is None:
            b = OxmlElement("w:tcBorders")
            tcPr.append(b)
        for lado, val in lados.items():
            el = OxmlElement(f"w:{lado}")
            el.set(qn("w:val"), val)
            el.set(qn("w:sz"), "6")
            el.set(qn("w:color"), "000000")
            b.append(el)

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.top_margin, sec.left_margin, sec.bottom_margin, sec.right_margin = Cm(3), Cm(3), Cm(2), Cm(2)
    st = doc.styles["Normal"]
    st.font.name = "Arial"
    st.font.size = Pt(10)
    if sintetico:
        p = doc.add_paragraph()
        r = p.add_run(AVISO_SINT)
        r.bold, r.font.color.rgb = True, RGBColor(0xB0, 0x47, 0x5B)
    for t in tabelas:
        p = doc.add_paragraph()
        p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(12), Pt(3)
        p.paragraph_format.keep_with_next = True
        p.add_run(t.titulo)
        tab = doc.add_table(rows=1 + len(t.linhas), cols=len(t.cab))
        tab.alignment = WD_TABLE_ALIGNMENT.CENTER
        tab.autofit = False
        quadro = t.tipo == "Quadro"
        # largura das colunas proporcional ao maior texto (min. 1,8 cm; total = 16 cm uteis da pagina)
        maior = [max([len(str(h)) for h in [t.cab[j]] + [li[j] for li in t.linhas]] + [3])
                 for j in range(len(t.cab))]
        larg = [max(1.8, 16.0 * m / sum(maior)) for m in maior]
        larg = [w * 16.0 / sum(larg) for w in larg]
        for j, w in enumerate(larg):
            for c in tab.columns[j].cells:
                c.width = Cm(w)
        # LibreOffice e algumas versoes do Word leem a largura da grade (tblGrid), nao a da celula
        for j, gc in enumerate(tab._tbl.tblGrid.findall(qn("w:gridCol"))):
            gc.set(qn("w:w"), str(int(larg[j] / 2.54 * 1440)))
        for j, h in enumerate(t.cab):
            c = tab.cell(0, j)
            c.text = ""
            run = c.paragraphs[0].add_run(h)
            run.bold = True
        for i, li in enumerate(t.linhas, start=1):
            for j, v in enumerate(li):
                tab.cell(i, j).text = str(v)
        for i, row in enumerate(tab.rows):
            for j, c in enumerate(row.cells):
                for par in c.paragraphs:
                    par.alignment = WD_ALIGN_PARAGRAPH.LEFT if (j == 0 or quadro or len(t.cab) == 3) \
                        else WD_ALIGN_PARAGRAPH.CENTER
                    par.paragraph_format.space_after = Pt(0)
                    for run in par.runs:
                        run.font.size = Pt(9)
                if quadro:  # quadro: grade completa
                    borda(c, top="single", bottom="single", left="single", right="single")
                else:       # tabela (IBGE): linhas no topo, abaixo do cabecalho e no fim; laterais abertas
                    lados = {"left": "nil", "right": "nil"}
                    if i == 0:
                        lados.update(top="single", bottom="single")
                    if i == len(tab.rows) - 1:
                        lados.update(bottom="single")
                    borda(c, **lados)
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(3)
        r = p.add_run(FONTE.format(ano=ano) + (f" Nota: {t.nota}" if t.nota else ""))
        r.font.size = Pt(9)
    doc.save(caminho)
    return True


if __name__ == "__main__":
    sys.exit(main())
