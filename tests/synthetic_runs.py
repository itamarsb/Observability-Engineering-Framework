"""Gera execucoes SINTETICAS no mesmo formato da bancada, para testar o pipeline offline.

ATENCAO: nada aqui e medicao. Os arquivos levam "synthetic": true no manifest.json,
kind = "synthetic" e run_id com prefixo SINT-. As figuras e tabelas detectam isso e
aplicam marca d'agua / prefixo SINTETICO_ automaticamente, sem opcao de desligar.

Uso (demonstracao completa, fora do repositorio):
  python3 tests/synthetic_runs.py <pasta_destino> [--rapido]
Cria <pasta_destino>/campaign/SINT-C*-r0*-*/ (18 execucoes + 1 invalida de exemplo), todas com
notes.md PENDENTE como na bancada (a classificacao fica para scripts/revisar_execucoes.py).
De proposito: a 1a tentativa de C2-r02 falha (INVALIDA automatica) e C3-r03 tem dropped_iterations
(INCONCLUSIVA, para treinar a decisao do operador).
e <pasta_destino>/pilot/SINT-RAMP-*/ e roda o analyze_run.py real em cada execucao.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Parametros ficticios, so para exercitar o codigo (nao sao expectativas do experimento).
CENARIOS = {
    "C0": {"rate": 16, "int": "none", "lat": 25.0, "sig": 0.28},
    "C2": {"rate": 35, "int": "none", "lat": 32.0, "sig": 0.33},
    "C3": {"rate": 60, "int": "none", "lat": 55.0, "sig": 0.48, "falha": 0.004, "drop": 0.002},
    "C4": {"rate": 16, "int": "cpu", "args": "90", "lat": 25.0, "sig": 0.28},
    "C5": {"rate": 16, "int": "mem", "args": "4G 5G", "lat": 25.0, "sig": 0.28},
    "C6": {"rate": 16, "int": "net", "args": "100", "lat": 25.0, "sig": 0.28},
}
ORDEM_BLOCOS = [["C0", "C2", "C3", "C4", "C5", "C6"],
                ["C2", "C4", "C6", "C3", "C0", "C5"],
                ["C5", "C3", "C6", "C0", "C2", "C4"]]
GIB = 2**30
DIGEST = "b8e7c92320f2bcd4365ebfe78b8ea6901477135536232c823eba2c44ccb70a7e"


def iso(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec="microseconds")


def stamp(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def prom_json(pontos: list[tuple[float, float]], metric: dict | None = None) -> dict:
    return {"status": "success", "data": {"resultType": "matrix", "result": [
        {"metric": metric or {}, "values": [[round(t, 3), f"{v:.6g}"] for t, v in pontos]}]}}


def suavizar(valores: list[float], n: int = 6) -> list[float]:
    """Imita o atraso de rate(...[30s]) com amostras de 5 s."""
    out = []
    for i in range(len(valores)):
        janela = valores[max(0, i - n + 1): i + 1]
        out.append(sum(janela) / len(janela))
    return out


def gerar_execucao(base: Path, cen: str, rep: str, t0: float, rng: random.Random,
                   W: int, P: int, invalida: bool = False) -> Path:
    c = CENARIOS[cen]
    off = round(rng.uniform(-0.02, 0.02), 4)
    inter = c["int"] != "none"
    total = W + P + (P + P if inter else 0)
    run_id = f"SINT-{cen}-{rep}-{stamp(t0)}"
    d = base / run_id
    (d / "server").mkdir(parents=True)
    s0 = t0 + W + P + 0.35 if inter else None
    s1 = s0 + P + 0.05 if inter else None

    def fator(t: float) -> tuple[float, float, float]:
        """(multiplicador interno, acrescimo de rede ms, acrescimo upstream ms)"""
        if not inter or not (s0 <= t < s1):
            return 1.0, 0.0, 0.0
        if c["int"] == "cpu":
            return 3.1, 0.0, 0.0
        if c["int"] == "mem":
            return 1.07, 0.0, 0.0
        return 1.0, 200.0, 100.0

    k6, loki, ngx = [], [], []
    n_req = int(total * c["rate"])
    falhas = 0
    for i in range(n_req):
        ini = t0 + 1.2 + i / c["rate"]
        mult, rede, upx = fator(ini)
        interno = rng.lognormvariate(math.log(c["lat"] * 0.82), c["sig"]) * mult
        cliente = interno + rng.uniform(2.0, 5.0) + rede
        fim = ini + cliente / 1000
        if rep == "r03" and rng.random() < c.get("drop", 0) * (2 if fim - t0 > W else 0):
            k6.append({"type": "Point", "metric": "dropped_iterations",
                       "data": {"time": iso(ini), "value": 1, "tags": {"scenario": "work"}}})
            continue
        falhou = invalida and W + P / 2 < fim - t0 < W + P / 2 + 20 or rng.random() < c.get("falha", 0)
        falhas += falhou
        k6.append({"type": "Point", "metric": "failed",
                   "data": {"time": iso(fim), "value": int(falhou), "tags": {"name": "GET /work"}}})
        if not falhou:
            k6.append({"type": "Point", "metric": "ok_duration",
                       "data": {"time": iso(fim), "value": round(cliente, 3), "tags": {"name": "GET /work"}}})
        tid = f"{rng.getrandbits(128):032x}"
        t_srv = ini + (cliente - rede / 2 - 1.0) / 1000 + off
        loki.append({"ts_ns": int(t_srv * 1e9), "line": "request_completed",
                     "fields": {"service_name": "tcc2-api"},
                     "structured_metadata": {"event": "request_completed", "route": "/work",
                                             "status_code": "503" if falhou else "200",
                                             "duration_ms": f"{interno:.3f}", "run_id": run_id,
                                             "trace_id": tid}})
        ngx.append((t_srv + 0.001, {"time": iso(t_srv), "status": 503 if falhou else 200,
                                    "request_time": round((interno + 0.6 + upx) / 1000, 3),
                                    "upstream_response_time": f"{(interno + 0.4 + upx) / 1000:.3f}",
                                    "run_id": run_id}))
    k6.sort(key=lambda p: p["data"]["time"])
    with open(d / "k6-raw.json", "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "Metric", "metric": "failed", "data": {"name": "failed", "type": "rate"}}) + "\n")
        for p in k6:
            fh.write(json.dumps(p) + "\n")
    with open(d / "server" / "loki-api.jsonl", "w", encoding="utf-8") as fh:
        for e in sorted(loki, key=lambda e: e["ts_ns"]):
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(d / "server" / "nginx.log", "w", encoding="utf-8") as fh:
        for t, j in sorted(ngx, key=lambda x: x[0]):
            fh.write(f"{dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat().replace('+00:00', 'Z')} "
                     f"{json.dumps(j)}\n")

    # Sonda a cada 5 s
    with open(d / "probe.csv", "w", encoding="utf-8") as fh:
        fh.write("run_id,seq,scheduled_utc,started_utc,finished_utc,duration_ms,http_status,"
                 "body_ok,success,transport_error,missed,lateness_ms\n")
        k = 0
        t = t0 - 2
        while t < t0 + total + 20:
            mult, rede, _ = fator(t)
            ms = rng.lognormvariate(math.log(c["lat"]), 0.2) * mult + rede
            fh.write(f"{run_id},{k},{iso(t)},{iso(t + 0.0004)},{iso(t + ms / 1000)},{ms:.3f},200,"
                     f"true,true,,false,0.4\n")
            k += 1
            t += 5

    # Series do Prometheus (relogio do servidor)
    ts = [t0 - 60 + off + 5 * i for i in range(int((total + 110) / 5))]
    cpu_base = 3 + c["rate"] * 0.55
    cpu = [cpu_base + rng.gauss(0, 1.2) + (88 - cpu_base if c["int"] == "cpu" and s0 + off <= t < s1 + off else 0)
           for t in ts]
    mem = [13.6 * GIB + rng.gauss(0, 0.03 * GIB) - (4.05 * GIB if c["int"] == "mem" and s0 + off <= t < s1 + off else 0)
           for t in ts]
    swap = [0.012 * GIB for _ in ts]
    p95s = [c["lat"] * 1.4 * (3.1 if c["int"] == "cpu" and s0 + off <= t < s1 + off else 1) for t in ts]
    for nome, vals in (("cpu_host_pct", suavizar([min(100, max(0, v)) for v in cpu])),
                       ("mem_available_bytes", suavizar(mem)), ("swap_used_bytes", swap),
                       ("mem_used_pct", [100 * (1 - v / (15.5 * GIB)) for v in suavizar(mem)]),
                       ("p95_server_ms", suavizar(p95s))):
        json.dump(prom_json(list(zip(ts, vals))), open(d / "server" / f"prom-{nome}.json", "w"), indent=1)
    json.dump([{"name": f"tcc2-{s}-1", "service": s, "image": f"{s}:sint", "image_id": "sha256:sint",
                "status": "running", "restart_count": 0, "oom_killed": False, "started_at": iso(t0 - 3600)}
               for s in ("nginx", "api", "collector", "prometheus", "loki", "tempo", "grafana", "node-exporter")],
              open(d / "server" / "containers-state.json", "w"), indent=1)
    (d / "server" / "kernel.log").write_text("-- No entries --\n", encoding="utf-8")
    json.dump({"script": "export_run/1.0", "run_id": run_id, "items": {"sintetico": {"series": 1}}},
              open(d / "server" / "export-report.json", "w"), indent=1)
    if inter:
        det = {"cpu": "cpu=0 cpu-load=90 timeout=180s", "mem": "vm=1 vm-bytes=4G MemoryMax=5G timeout=180s",
               "net": "netem delay=100ms nginx_pid=4242"}[c["int"]]
        (d / "events-server.csv").write_text(
            f"event,timestamp_utc,detail\nstress_start,{iso(s0 + off)},{det}\nstress_end,{iso(s1 + off)},rc=0\n",
            encoding="utf-8")

    # vmstat do gerador (com -t, em UTC)
    with open(d / "notebook-vmstat.txt", "w", encoding="utf-8") as fh:
        fh.write("procs -----------memory---------- ---swap-- -----io---- -system-- -------cpu------- "
                 "-----timestamp-----\n r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy "
                 "id wa st gu                 UTC\n")
        t = t0 - 2
        while t < t0 + total + 20:
            ocioso = max(0, min(100, round(100 - (4 + c["rate"] * 0.7 + rng.gauss(0, 1.5)))))
            hora = dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            fh.write(f" 1  0      0 6000000  10000 900000    0    0     0     2  900 1500 {100 - ocioso} 0 "
                     f"{ocioso}  0  0  0 {hora}\n")
            t += 5

    man = {
        "run_id": run_id, "scenario": cen, "scenario_name": f"{cen} (sintetico)", "repetition": rep,
        "kind": "synthetic", "synthetic": True, "protocol_version": "SINTETICO",
        "commit": "0" * 40, "git_clean": True, "base_url": "http://sintetico:8080", "n": 20000,
        "expected_digest": DIGEST, "rate_rps": float(c["rate"]), "warmup_s": W, "phase_s": P,
        "intervention": c["int"], "intervention_args": c.get("args", ""),
        "intervention_duration_s": P, "total_s": total, "http_timeout": "2s", "pre_vus": 50, "max_vus": 100,
        "probe_interval_s": 5.0, "probe_timeout_s": 2.0, "clock_offset_s": off, "compose_project": "tcc2",
        "generator": {"host": "sintetico", "kernel": "-", "k6": "-", "python": "-"},
        "k6_start_utc": iso(t0), "end_utc": iso(t0 + total + 22), "k6_exit_code": 99 if invalida else 0,
        "intervention_rc": 0 if inter else None,
    }
    json.dump(man, open(d / "manifest.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    (d / "k6-exit-code.txt").write_text("99\n" if invalida else "0\n")
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "analyze_run.py"), str(d)],
                       capture_output=True, text=True)
    (d / "analysis.txt").write_text(p.stdout + p.stderr, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"analyze_run falhou em {d}: {p.stderr}")
    # mesmo modelo de notes.md gravado pelo run_scenario.sh
    nota = (f"# Notas da execucao {run_id}\n- Classificacao final: PENDENTE\n"
            "- Validade da carga (k6 exit, dropped_iterations, CPU do notebook): PENDENTE\n"
            "- Validade da sonda (cobertura = 100%?): PENDENTE\n"
            "- Validade da telemetria (lacunas, reinicios, OOM, export-report): PENDENTE\n"
            "- Intervencao aplicada como planejado? (events-server.csv, intervention.log): PENDENTE\n"
            "- Incidentes / observacoes do operador:\n")
    if invalida:
        nota += "INVALIDA: falha tecnica automatica (k6=99; exemplo sintetico)\n"
    (d / "notes.md").write_text(nota, encoding="utf-8")
    escrever_checksums(d)
    return d


def escrever_checksums(d: Path) -> None:
    linhas = []
    for f in sorted(d.rglob("*")):
        rel = "./" + f.relative_to(d).as_posix()
        if f.is_file() and f.name not in ("checksums.sha256", "notes.md", "analysis.txt") \
                and not rel.startswith("./analysis/"):
            linhas.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {rel}")
    (d / "checksums.sha256").write_text("\n".join(linhas) + "\n", encoding="utf-8")


def gerar_rampa(base: Path, t0: float, rng: random.Random, step_s: int) -> Path:
    steps = [10, 20, 40, 60, 80, 100, 120]
    cap = 86.0
    run_id = f"SINT-RAMP-{stamp(t0)}"
    d = base / run_id
    (d / "server").mkdir(parents=True)
    k6, cpu_srv = [], []
    t = t0 + 1.0
    alvo_ant = steps[0]
    for alvo in steps:
        for fase_s, inicio, fim in ((10, alvo_ant, alvo), (step_s, alvo, alvo)):
            fim_t = t + fase_s
            while t < fim_t:
                frac = 1 - (fim_t - t) / fase_s
                taxa = inicio + (fim - inicio) * frac
                servido = min(taxa, cap)
                carga = servido / cap
                lat = 24 / max(0.04, 1 - min(carga, 0.985)) ** 0.55
                for _ in range(int(servido)):
                    ms = rng.lognormvariate(math.log(lat), 0.3)
                    k6.append(("failed", t + ms / 1000, 0))
                    k6.append(("ok_duration", t + ms / 1000, round(ms, 3)))
                for _ in range(int(taxa - servido)):
                    k6.append(("dropped_iterations", t, 1))
                t += 1
            alvo_ant = alvo
    with open(d / "k6-raw.json", "w", encoding="utf-8") as fh:
        for m, tt, v in sorted(k6, key=lambda x: x[1]):
            fh.write(json.dumps({"type": "Point", "metric": m, "data": {"time": iso(tt), "value": v}}) + "\n")
    fim_total = t
    # CPU do servidor (Prometheus) e do gerador (vmstat)
    ts = [t0 - 30 + 5 * i for i in range(int((fim_total - t0 + 60) / 5))]

    def taxa_em(x: float) -> float:
        rel = x - t0
        i = int(rel // (step_s + 10))
        if rel < 0 or i >= len(steps):
            return 0.0
        return min(steps[i], cap)
    for x in ts:
        cpu_srv.append(min(99, 3 + 1.1 * taxa_em(x) + rng.gauss(0, 1)))
    json.dump(prom_json(list(zip(ts, suavizar(cpu_srv)))), open(d / "server" / "prom-cpu_host_pct.json", "w"))
    with open(d / "notebook-vmstat.txt", "w", encoding="utf-8") as fh:
        fh.write("procs -----------memory---------- ---swap-- -----io---- -system-- -------cpu------- "
                 "-----timestamp-----\n r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy "
                 "id wa st gu                 UTC\n")
        for x in [t0 - 2 + 5 * i for i in range(int((fim_total - t0 + 10) / 5))]:
            rel = x - t0
            i = min(len(steps) - 1, max(0, int(rel // (step_s + 10))))
            ocioso = max(0, min(100, round(100 - (6 + steps[i] * 0.55 + rng.gauss(0, 1.5)))))
            hora = dt.datetime.fromtimestamp(x, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            fh.write(f" 1  0      0 6000000  10000 900000    0    0     0     2  900 1500 {100 - ocioso} 0 "
                     f"{ocioso}  0  0  0 {hora}\n")
    man = {"run_id": run_id, "scenario": "RAMP", "repetition": "r01", "kind": "synthetic", "synthetic": True,
           "protocol_version": "SINTETICO", "steps": steps, "step_s": step_s, "k6_start_utc": iso(t0),
           "end_utc": iso(fim_total + 5), "clock_offset_s": 0.0, "k6_exit_code": 0}
    json.dump(man, open(d / "manifest.json", "w", encoding="utf-8"), indent=2)
    escrever_checksums(d)
    return d


def gerar_tudo(destino: Path, rapido: bool = False, seed: int = 20261107) -> dict:
    rng = random.Random(seed)
    W, P = (10, 30) if rapido else (60, 180)
    camp = destino / "campaign"
    camp.mkdir(parents=True, exist_ok=True)
    t = dt.datetime(2026, 11, 7, 12, 0, tzinfo=dt.timezone.utc).timestamp()
    pastas = []
    for b, ordem in enumerate(ORDEM_BLOCOS, start=1):
        for cen in ordem:
            rep = f"r{b:02d}"
            if cen == "C2" and rep == "r02":  # exemplo de execucao invalida, depois refeita
                pastas.append(gerar_execucao(camp, cen, rep, t, rng, W, P, invalida=True))
                t += 900
            pastas.append(gerar_execucao(camp, cen, rep, t, rng, W, P))
            t += 900
    rampa = gerar_rampa(destino / "pilot", t + 3600, rng, 20 if rapido else 60)
    return {"campanha": camp, "execucoes": pastas, "rampa": rampa}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("destino")
    ap.add_argument("--rapido", action="store_true", help="fases curtas (10 s + 30 s), para testes")
    a = ap.parse_args()
    r = gerar_tudo(Path(a.destino), a.rapido)
    print(f"{len(r['execucoes'])} execucoes sinteticas em {r['campanha']}; rampa em {r['rampa']}")
