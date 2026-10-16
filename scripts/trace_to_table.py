#!/usr/bin/env python3
"""Converte um trace exportado do Tempo (/api/v2/traces/<id>) em tabela legivel (CSV + tela).
O Tempo grava spanId/parentSpanId em base64; aqui eles viram hexadecimal (como no Grafana).
Uso: python3 scripts/trace_to_table.py server/traces/<trace_id>.json [saida.csv]
"""
import base64
import csv
import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
tr = d.get("trace", d)
rows = []
for rs in tr.get("resourceSpans", []):
    svc = next((a["value"].get("stringValue") for a in rs["resource"]["attributes"] if a["key"] == "service.name"), "")
    for ss in rs.get("scopeSpans", []):
        for sp in ss["spans"]:
            hexid = lambda b: base64.b64decode(b).hex() if b else ""
            attrs = {a["key"]: list(a["value"].values())[0] for a in sp.get("attributes", [])}
            rows.append({
                "trace_id": hexid(sp["traceId"]), "span_id": hexid(sp["spanId"]),
                "parent_span_id": hexid(sp.get("parentSpanId", "")), "nome": sp["name"],
                "tipo": sp.get("kind", "").replace("SPAN_KIND_", ""),
                "duracao_ms": round((int(sp["endTimeUnixNano"]) - int(sp["startTimeUnixNano"])) / 1e6, 3),
                "status": sp.get("status", {}).get("code", "UNSET").replace("STATUS_CODE_", ""),
                "servico": svc, "run_id": attrs.get("tcc2.run_id", ""),
                "http_status": attrs.get("http.response.status_code", ""),
            })
rows.sort(key=lambda r: (r["parent_span_id"] != "", r["nome"]))
for r in rows:
    print(f"{r['nome']:<18} span={r['span_id']} pai={r['parent_span_id'] or '-':<16} {r['duracao_ms']:>9} ms {r['status']}")
if len(sys.argv) > 2:
    with open(sys.argv[2], "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
