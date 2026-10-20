#!/usr/bin/env python3
"""Consolida todas as execucoes analisadas de uma campanha.

Le runs/<tipo>/*/analysis/phases.csv e summary.json e gera em results/processed/:
  summary-runs.csv       uma linha por execucao e fase (tabela do Apendice E)
  summary-scenarios.csv  por cenario e fase: mediana, minimo e maximo das repeticoes
                         (NAO e a media de P99: os valores por repeticao ficam em summary-runs.csv)
Execucoes cujo notes.md contenha a linha "INVALIDA" sao listadas, mas excluidas da consolidacao.
Uso: python3 scripts/consolidate.py runs/campaign results/processed
"""

from __future__ import annotations

import csv
import glob
import json
import os
import re
import statistics
import sys

METRICS = ["p95_ms", "p99_ms", "erro_composto_pct", "vazao_sucesso_rps", "vazao_observada_rps",
           "disponibilidade_pct", "cobertura_pct", "respostas_corretas", "dropped_iterations"]


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else "runs/campaign"
    dst = sys.argv[2] if len(sys.argv) > 2 else "results/processed"
    os.makedirs(dst, exist_ok=True)
    rows, excluded = [], []
    seen: set[tuple[str,str]] = set()
    for run in sorted(glob.glob(os.path.join(src, "*"))):
        ph = os.path.join(run, "analysis", "phases.csv")
        if not os.path.exists(ph):
            excluded.append((os.path.basename(run), "sem analise"))
            continue
        notes = os.path.join(run, "notes.md")
        if not os.path.exists(notes):
            excluded.append((os.path.basename(run), "sem notes.md"))
            continue
        note_text = open(notes, encoding="utf-8").read()
        status = re.findall(r"(?im)^\s*-\s*Classificacao final:\s*(VALIDA|INVALIDA|PENDENTE)\s*$", note_text)
        if len(status) != 1 or status[0] != "VALIDA" or "INVALIDA:" in note_text:
            excluded.append((os.path.basename(run), "sem aprovacao explicita ou invalida"))
            continue
        manifest_path = os.path.join(run, "manifest.json")
        if not os.path.exists(manifest_path):
            excluded.append((os.path.basename(run), "sem manifest.json"))
            continue
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        key = (manifest["scenario"], manifest["repetition"])
        if key in seen:
            print(f"ERRO: mais de uma execucao VALIDA para o mesmo cenario/repeticao {key}; "
                  "identifique a repeticao definitiva e invalide a substituida")
            return 2
        seen.add(key)
        extra = {}
        sj = os.path.join(run, "analysis", "summary.json")
        if os.path.exists(sj):
            s = json.load(open(sj, encoding="utf-8"))
            extra = {"delta_p95_ms": s.get("delta_p95_ms"), "recuperacao_s": s.get("recuperacao_s"),
                     "recuperacao_status": s.get("recuperacao_status")}
        for r in csv.DictReader(open(ph, encoding="utf-8")):
            rows.append({**r, **extra})
    if not rows:
        print("nenhuma execucao analisada encontrada")
        return 1
    with open(os.path.join(dst, "summary-runs.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    groups: dict[tuple, list] = {}
    for r in rows:
        if r["fase"] == "aquecimento":
            continue
        groups.setdefault((r["cenario"], r["fase"]), []).append(r)
    out = []
    for (cen, fase), rs in sorted(groups.items()):
        line = {"cenario": cen, "fase": fase, "repeticoes": len(rs)}
        for m in METRICS:
            vals = [float(r[m]) for r in rs if r.get(m) not in (None, "", "None")]
            line[f"{m}_mediana"] = round(statistics.median(vals), 3) if vals else None
            line[f"{m}_min"] = round(min(vals), 3) if vals else None
            line[f"{m}_max"] = round(max(vals), 3) if vals else None
        out.append(line)
    with open(os.path.join(dst, "summary-scenarios.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"{len(rows)} linhas (execucao x fase); {len(out)} grupos; excluidas: {excluded or 'nenhuma'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
