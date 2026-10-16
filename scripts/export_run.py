#!/usr/bin/env python3
"""Exporta, NO SERVIDOR, os dados de uma execucao para ~/tcc2-exports/<RUN_ID>/.

Chamado pelo orquestrador (notebook) via SSH, logo apos o fim da execucao.
Usa somente a biblioteca padrao. Precisa: Prometheus/Loki/Tempo em 127.0.0.1,
usuario no grupo docker (estado dos conteineres) e no grupo adm (journalctl).

Gera:
  prom-<nome>.json + queries.txt     series (query_range, step 5 s)
  loki-api.jsonl                     logs da API com o run_id (paginado)
  tempo-search-*.json, traces/*.json traces selecionados (amostra, erros, lentos)
  containers-state.json              RestartCount, OOMKilled, status, imagem
  nginx.log, collector.log, api.log  logs dos conteineres na janela
  kernel.log, stress-units.log       journalctl (OOM e unidades tcc2-*)
  system-snapshot.txt                free, swap, df, uptime, sensores
  export-report.json                 status de cada item + 1a/ultima amostra

Uso: python3 scripts/export_run.py --run-id C4-r01-... --start 2026-10-20T18:00:00Z --end 2026-10-20T18:11:00Z
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

VERSION = "export_run/1.0"

PROM_QUERIES = {
    # SLIs vistos pelo servidor (estimativas por histograma; a fonte primaria e o k6)
    "rps_work": 'sum(rate(http_server_request_duration_seconds_count{job="tcc2-api",http_route="/work"}[30s]))',
    "p95_server_ms": '1000 * histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket{job="tcc2-api",http_route="/work"}[30s])))',
    "p99_server_ms": '1000 * histogram_quantile(0.99, sum by (le) (rate(http_server_request_duration_seconds_bucket{job="tcc2-api",http_route="/work"}[30s])))',
    # "or vector(0)": com trafego e sem 5xx o resultado e 0; sem trafego fica vazio ("sem amostras")
    "err5xx_pct": '100 * (sum(rate(http_server_request_duration_seconds_count{job="tcc2-api",http_route="/work",http_response_status_code=~"5.."}[30s])) or vector(0)) / sum(rate(http_server_request_duration_seconds_count{job="tcc2-api",http_route="/work"}[30s]))',
    # Recursos do host fisico (Node Exporter)
    "cpu_host_pct": '100 * (1 - avg(rate(node_cpu_seconds_total{job="node",mode="idle"}[30s])))',
    "cpu_iowait_pct": '100 * avg(rate(node_cpu_seconds_total{job="node",mode="iowait"}[30s]))',
    "load1": 'node_load1{job="node"}',
    "mem_used_pct": '100 * (1 - node_memory_MemAvailable_bytes{job="node"} / node_memory_MemTotal_bytes{job="node"})',
    "mem_available_bytes": 'node_memory_MemAvailable_bytes{job="node"}',
    "swap_used_bytes": 'node_memory_SwapTotal_bytes{job="node"} - node_memory_SwapFree_bytes{job="node"}',
    "swap_io_pages": 'rate(node_vmstat_pswpin{job="node"}[30s]) + rate(node_vmstat_pswpout{job="node"}[30s])',
    "net_rx_bytes": 'sum by (device) (rate(node_network_receive_bytes_total{job="node",device!~"lo|veth.*|br-.*|docker.*"}[30s]))',
    "net_tx_bytes": 'sum by (device) (rate(node_network_transmit_bytes_total{job="node",device!~"lo|veth.*|br-.*|docker.*"}[30s]))',
    "temp_celsius": 'max(node_hwmon_temp_celsius{job="node"})',
    # Integridade da coleta (painel 03)
    "up": "up",
    "collector_spans_in": 'rate(otelcol_receiver_accepted_spans[30s])',
    "collector_logs_in": 'rate(otelcol_receiver_accepted_log_records[30s])',
    "collector_points_in": 'rate(otelcol_receiver_accepted_metric_points[30s])',
    "collector_refused": 'rate(otelcol_receiver_refused_spans[30s]) + rate(otelcol_receiver_refused_log_records[30s]) + rate(otelcol_receiver_refused_metric_points[30s])',
    "collector_send_failed": '{__name__=~"otelcol_exporter_send_failed_.*"}',
    "collector_queue_size": 'otelcol_exporter_queue_size',
}


def http_get_json(url: str, params: dict, timeout: float = 60.0):
    q = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{q}", timeout=timeout) as r:
        return json.loads(r.read())


def to_epoch(s: str) -> float:
    s = s.strip().replace("Z", "+00:00")
    return dt.datetime.fromisoformat(s).timestamp()


def run(cmd: list[str], out_path: str) -> dict:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(p.stdout)
            if p.stderr:
                fh.write("\n# stderr:\n" + p.stderr)
        return {"cmd": " ".join(cmd), "rc": p.returncode, "bytes": os.path.getsize(out_path)}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"cmd": " ".join(cmd), "rc": None, "error": repr(exc)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--start", required=True, help="UTC ISO (inicio da janela, com margem)")
    ap.add_argument("--end", required=True, help="UTC ISO (fim da janela, com margem)")
    ap.add_argument("--out-base", default=os.path.expanduser("~/tcc2-exports"))
    ap.add_argument("--project", default="tcc2")
    ap.add_argument("--prom", default="http://127.0.0.1:9090")
    ap.add_argument("--loki", default="http://127.0.0.1:3100")
    ap.add_argument("--tempo", default="http://127.0.0.1:3200")
    ap.add_argument("--slow-ms", type=int, default=100)
    a = ap.parse_args()

    out = os.path.join(a.out_base, a.run_id)
    os.makedirs(os.path.join(out, "traces"), exist_ok=True)
    t0, t1 = to_epoch(a.start), to_epoch(a.end)
    report = {"script": VERSION, "run_id": a.run_id, "start": a.start, "end": a.end, "items": {}}

    # 1) Prometheus
    with open(os.path.join(out, "queries.txt"), "w", encoding="utf-8") as qf:
        qf.write(f"# janela {a.start} -> {a.end} step=5s\n")
        for name, q in PROM_QUERIES.items():
            qf.write(f"{name}\t{q}\n")
            try:
                d = http_get_json(f"{a.prom}/api/v1/query_range", {"query": q, "start": t0, "end": t1, "step": "5s"})
                json.dump(d, open(os.path.join(out, f"prom-{name}.json"), "w"), indent=1)
                res = d.get("data", {}).get("result", [])
                ts = [float(v[0]) for s in res for v in s.get("values", [])]
                report["items"][f"prom-{name}"] = {
                    "series": len(res), "samples": len(ts),
                    "first": dt.datetime.fromtimestamp(min(ts), dt.timezone.utc).isoformat() if ts else None,
                    "last": dt.datetime.fromtimestamp(max(ts), dt.timezone.utc).isoformat() if ts else None,
                }
            except Exception as exc:  # registra e continua
                report["items"][f"prom-{name}"] = {"error": repr(exc)}

    # 2) Loki (paginado, ordem crescente)
    logq = '{service_name="tcc2-api"} | run_id=~"' + a.run_id + '.*"'
    n_lines, start_ns, end_ns = 0, int(t0 * 1e9), int(t1 * 1e9)
    try:
        with open(os.path.join(out, "loki-api.jsonl"), "w", encoding="utf-8") as lf:
            cursor = start_ns
            while True:
                d = http_get_json(f"{a.loki}/loki/api/v1/query_range", {
                    "query": logq, "start": cursor, "end": end_ns, "limit": 5000, "direction": "forward"})
                entries = []
                for s in d["data"]["result"]:
                    for ts, line in s["values"]:
                        entries.append((int(ts), line, s["stream"]))
                entries.sort(key=lambda e: e[0])
                for ts, line, stream in entries:
                    lf.write(json.dumps({"ts_ns": ts, "line": line, "fields": stream}, ensure_ascii=False) + "\n")
                n_lines += len(entries)
                if len(entries) < 5000:
                    break
                cursor = entries[-1][0] + 1  # proxima pagina apos o ultimo timestamp
        report["items"]["loki-api"] = {"query": logq, "lines": n_lines}
    except Exception as exc:
        report["items"]["loki-api"] = {"query": logq, "error": repr(exc)}

    # 3) Tempo: buscas e traces completos selecionados
    searches = {
        "amostra": '{ span.tcc2.run_id = "%s" }' % a.run_id,
        "erros": '{ span.tcc2.run_id =~ "%s.*" && status = error }' % a.run_id,
        "lentos": '{ span.tcc2.run_id =~ "%s.*" && duration > %dms }' % (a.run_id, a.slow_ms),
    }
    ids: set[str] = set()
    for name, q in searches.items():
        try:
            d = http_get_json(f"{a.tempo}/api/search", {"q": q, "start": int(t0), "end": int(t1) + 1, "limit": 10})
            json.dump(d, open(os.path.join(out, f"tempo-search-{name}.json"), "w"), indent=1)
            # o Tempo pode omitir zeros a esquerda do traceID: normaliza para 32 hex
            found = [t["traceID"].zfill(32) for t in d.get("traces", [])]
            ids.update(found)
            report["items"][f"tempo-search-{name}"] = {"query": q, "traces": len(found)}
        except Exception as exc:
            report["items"][f"tempo-search-{name}"] = {"query": q, "error": repr(exc)}
    ok = 0
    for tid in sorted(ids):
        try:
            d = http_get_json(f"{a.tempo}/api/v2/traces/{tid}", {})
            json.dump(d, open(os.path.join(out, "traces", f"{tid}.json"), "w"), indent=1)
            ok += 1
        except Exception:
            pass
    report["items"]["tempo-traces"] = {"selected": len(ids), "saved": ok}

    # 4) Conteineres, logs e sistema
    since = dt.datetime.fromtimestamp(t0, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = dt.datetime.fromtimestamp(t1, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        ps = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={a.project}"],
                            capture_output=True, text=True, timeout=60).stdout.split()
        state = []
        if ps:
            insp = json.loads(subprocess.run(["docker", "inspect", *ps], capture_output=True, text=True, timeout=60).stdout)
            for c in insp:
                state.append({
                    "name": c["Name"].lstrip("/"),
                    "service": c["Config"]["Labels"].get("com.docker.compose.service"),
                    "image": c["Config"]["Image"], "image_id": c["Image"],
                    "status": c["State"]["Status"], "restart_count": c.get("RestartCount"),
                    "oom_killed": c["State"].get("OOMKilled"), "started_at": c["State"].get("StartedAt"),
                })
        json.dump(state, open(os.path.join(out, "containers-state.json"), "w"), indent=1)
        report["items"]["containers-state"] = {"containers": len(state),
                                               "restarts": sum((s["restart_count"] or 0) for s in state),
                                               "oom_killed": [s["name"] for s in state if s["oom_killed"]]}
        for svc in ("nginx", "collector", "api"):
            cid = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={a.project}",
                                  "--filter", f"label=com.docker.compose.service={svc}"],
                                 capture_output=True, text=True, timeout=60).stdout.split()
            if cid:
                report["items"][f"{svc}.log"] = run(["docker", "logs", "--timestamps", "--since", since,
                                                     "--until", until, cid[0]], os.path.join(out, f"{svc}.log"))
    except Exception as exc:
        report["items"]["containers-state"] = {"error": repr(exc)}

    report["items"]["kernel.log"] = run(["journalctl", "-k", "--no-pager", "-o", "short-iso-precise",
                                         "--since", f"@{int(t0)}", "--until", f"@{int(t1) + 1}"],
                                        os.path.join(out, "kernel.log"))
    report["items"]["stress-units.log"] = run(["journalctl", "--no-pager", "-o", "short-iso-precise",
                                               "-u", "tcc2-cpu", "-u", "tcc2-mem",
                                               "--since", f"@{int(t0)}", "--until", f"@{int(t1) + 1}"],
                                              os.path.join(out, "stress-units.log"))
    with open(os.path.join(out, "system-snapshot.txt"), "w", encoding="utf-8") as fh:
        for cmd in (["date", "-u"], ["uptime"], ["free", "-b"], ["swapon", "--show"], ["df", "-hT", "/"],
                    ["sensors"]):
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                fh.write(f"$ {' '.join(cmd)}\n{p.stdout}{p.stderr}\n")
            except OSError as exc:
                fh.write(f"$ {' '.join(cmd)}\n(indisponivel: {exc})\n\n")

    json.dump(report, open(os.path.join(out, "export-report.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in report["items"].items() if "error" in v}, ensure_ascii=False) or "{}")
    print(f"{VERSION}: exportado em {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
