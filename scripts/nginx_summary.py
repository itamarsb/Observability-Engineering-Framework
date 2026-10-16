#!/usr/bin/env python3
"""Resume o log JSON do NGINX de uma execucao por fase (util para o cenario C6).

Mostra request_time e upstream_response_time do NGINX por fase. No C6 (netem na saida
do NGINX), espera-se: upstream_response_time ~ +100 ms (o trecho NGINX -> API passa pela
eth0 atrasada), latencia do k6 ~ +200 ms (ida a API + resposta ao cliente) e duracao do
span GET /work estavel. Valores aproximados: confirme no piloto.
Le <run>/server/nginx.log (docker logs --timestamps) e as fases
de <run>/analysis/phases.csv (gerado por analyze_run.py). Horarios do servidor sao
convertidos para o relogio do notebook com o offset do manifest.
Uso: python3 scripts/nginx_summary.py <pasta_da_execucao>
"""
import csv
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_run import nearest_rank, parse_ts  # noqa: E402

d = sys.argv[1]
man = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
off = float(man.get("clock_offset_s") or 0)
phases = [(r["fase"], parse_ts(r["inicio_utc"]), parse_ts(r["fim_utc"]))
          for r in csv.DictReader(open(os.path.join(d, "analysis", "phases.csv"), encoding="utf-8"))]
recs = []
for line in open(os.path.join(d, "server", "nginx.log"), encoding="utf-8", errors="replace"):
    line = line.strip()
    if " {" not in line:
        continue
    ts, js = line.split(" ", 1)
    try:
        j = json.loads(js)
        t = parse_ts(ts) - off
        up = j.get("upstream_response_time", "-")
        recs.append((t, float(j["request_time"]) * 1000, None if up in ("-", "") else float(up.split(",")[-1]) * 1000,
                     int(j["status"]), j.get("run_id", "")))
    except (ValueError, KeyError):
        continue
print("fase,n,request_time_p50_ms,request_time_p95_ms,upstream_p50_ms,upstream_p95_ms,status_5xx")
for name, a, b in phases:
    rs = [r for r in recs if a <= r[0] < b and r[4].startswith(man["run_id"])]
    rt = [r[1] for r in rs]
    up = [r[2] for r in rs if r[2] is not None]
    e5 = sum(1 for r in rs if r[3] >= 500)
    f = lambda v, p: "" if not v else f"{nearest_rank(v, p):.1f}"
    print(f"{name},{len(rs)},{f(rt, .5)},{f(rt, .95)},{f(up, .5)},{f(up, .95)},{e5}")
