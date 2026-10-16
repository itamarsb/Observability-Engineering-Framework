#!/usr/bin/env python3
"""Analise de UMA execucao (run) do TCC2 - somente biblioteca padrao do Python.

Entrada (pasta da execucao, criada pelo orquestrador run_scenario.sh):
  manifest.json       parametros e horarios (k6_start_utc, warmup_s, phase_s, intervention,
                      clock_offset_s = relogio_servidor - relogio_notebook)
  k6-raw.json         saida --out json do k6 (pontos com horario de conclusao)
  probe.csv           sonda externa
  events-server.csv   (C4-C7) stress_start / stress_end gravados pelo SERVIDOR

Saida (subpasta analysis/, nunca sobrescreve os dados brutos):
  phases.csv          uma linha por fase: N, P95, P99, erro composto, vazao, sondas...
  windows.csv         serie de janelas de 5 s (para graficos)
  summary.json        resumo + recuperacao + efeito por repeticao (Delta P95)

Regras (congelar no protocolo antes da campanha):
  - Fases como intervalos [inicio, fim) pelo HORARIO DE CONCLUSAO da requisicao.
  - P95/P99 pelo metodo do posto mais proximo: x_(ceil(p*N)), N = respostas corretas.
  - Erro composto = 100 * falhas / tentativas (falha = status != 200 ou corpo incorreto,
    incluindo timeout e erro de conexao).
  - Disponibilidade amostrada so e comparada a meta se a cobertura da sonda = 100%.
Uso: python3 scripts/analyze_run.py <pasta_da_execucao> [--recovery-factor 1.2]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sys

VERSION = "analyze_run/1.0"


def parse_ts(s: str) -> float:
    """Converte ISO 8601 (com fuso, ate nanossegundos) em segundos Unix (float)."""
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # corta fracao de segundo com mais de 6 digitos (k6 usa nanossegundos)
    if "." in s:
        head, rest = s.split(".", 1)
        frac = ""
        i = 0
        while i < len(rest) and rest[i].isdigit():
            frac += rest[i]
            i += 1
        tz = rest[i:]
        s = f"{head}.{frac[:6].ljust(6, '0')}{tz}"
    return dt.datetime.fromisoformat(s).timestamp()


def iso(t: float) -> str:
    return dt.datetime.fromtimestamp(t, tz=dt.timezone.utc).isoformat(timespec="milliseconds")


def nearest_rank(values: list[float], p: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    k = max(1, math.ceil(p * len(v)))
    return v[k - 1]


def load_k6(path: str):
    attempts, oks, dropped = [], [], []  # (t, failed) ; (t, ms) ; (t, n)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if '"type":"Point"' not in line:
                continue
            p = json.loads(line)
            m = p.get("metric")
            if m not in ("failed", "ok_duration", "dropped_iterations"):
                continue
            t = parse_ts(p["data"]["time"])
            val = p["data"]["value"]
            if m == "failed":
                attempts.append((t, int(val)))
            elif m == "ok_duration":
                oks.append((t, float(val)))
            else:
                dropped.append((t, float(val)))
    return attempts, oks, dropped


def load_probe(path: str):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append({
                "t": parse_ts(r["scheduled_utc"]),
                "missed": r["missed"] == "true",
                "success": r["success"] == "true",
            })
    return rows


def load_events(path: str, offset_s: float) -> dict:
    """Le events-server.csv e converte para o relogio do notebook (t_cliente = t_servidor - offset)."""
    ev = {}
    if not os.path.exists(path):
        return ev
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ev[r["event"]] = parse_ts(r["timestamp_utc"]) - offset_s
    return ev


def phase_stats(name, a, b, attempts, oks, dropped, probe):
    dur = b - a
    att = [f for (t, f) in attempts if a <= t < b]
    lat = [ms for (t, ms) in oks if a <= t < b]
    drp = sum(n for (t, n) in dropped if a <= t < b)
    pr = [r for r in probe if a <= r["t"] < b]
    n_prev = len(pr)
    n_exec = sum(1 for r in pr if not r["missed"])
    n_ok = sum(1 for r in pr if r["success"])
    n_att, n_fail = len(att), sum(att)
    return {
        "fase": name,
        "inicio_utc": iso(a),
        "fim_utc": iso(b),
        "duracao_s": round(dur, 3),
        "tentativas": n_att,
        "falhas": n_fail,
        "respostas_corretas": len(lat),
        "p95_ms": _r(nearest_rank(lat, 0.95)),
        "p99_ms": _r(nearest_rank(lat, 0.99)),
        "erro_composto_pct": _r(100.0 * n_fail / n_att if n_att else None, 4),
        "vazao_observada_rps": _r(n_att / dur if dur > 0 else None),
        "vazao_sucesso_rps": _r(len(lat) / dur if dur > 0 else None),
        "dropped_iterations": int(drp),
        "sondas_previstas": n_prev,
        "sondas_executadas": n_exec,
        "sondas_corretas": n_ok,
        "cobertura_pct": _r(100.0 * n_exec / n_prev if n_prev else None),
        "disponibilidade_pct": _r(100.0 * n_ok / n_exec if n_exec else None),
        "disponibilidade_comparavel": bool(n_prev and n_exec == n_prev),
    }


def _r(x, nd=3):
    return None if x is None else round(x, nd)


def windows(a, b, attempts, oks, step=5.0):
    out = []
    t = a
    while t + step <= b + 1e-9:  # somente janelas completas (a ultima parcial e descartada)
        u = t + step
        lat = [ms for (tt, ms) in oks if t <= tt < u]
        att = [f for (tt, f) in attempts if t <= tt < u]
        out.append({
            "inicio_utc": iso(t), "t_rel_s": round(t - a, 1),
            "tentativas": len(att), "falhas": sum(att),
            "corretas": len(lat), "rps_sucesso": round(len(lat) / (u - t), 3),
            "p95_ms": _r(nearest_rank(lat, 0.95)), "p50_ms": _r(nearest_rank(lat, 0.50)),
        })
        t = u
    return out


def recovery(stress_end, end, attempts, oks, p95_before, factor, win=30.0, step=5.0, hold=60.0):
    """Tempo ate a 1a janela movel de 30 s com P95 <= factor*P95(antes) e zero falhas,
    mantida por 60 s (todas as janelas iniciadas em [u, u+60] satisfazem)."""
    if p95_before is None:
        return None, "sem_p95_antes"
    limit = factor * p95_before

    def ok_window(s):
        lat = [ms for (t, ms) in oks if s <= t < s + win]
        fails = sum(f for (t, f) in attempts if s <= t < s + win)
        p = nearest_rank(lat, 0.95)
        return p is not None and p <= limit and fails == 0

    u = stress_end
    while u + hold + win <= end + 1e-9:
        k = 0
        good = True
        while k * step <= hold + 1e-9:
            if not ok_window(u + k * step):
                good = False
                break
            k += 1
        if good:
            return round(u - stress_end, 1), "recuperado"
        u += step
    return None, "nao_recuperado_na_janela"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--recovery-factor", type=float, default=1.2)
    args = ap.parse_args()
    d = args.run_dir
    man = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    offset = float(man.get("clock_offset_s") or 0.0)
    t0 = parse_ts(man["k6_start_utc"])
    W, P = float(man["warmup_s"]), float(man["phase_s"])
    attempts, oks, dropped = load_k6(os.path.join(d, "k6-raw.json"))
    probe = load_probe(os.path.join(d, "probe.csv"))
    ev = load_events(os.path.join(d, "events-server.csv"), offset)
    k6_end = max([t for t, _ in attempts] + [t0 + W + P])

    phases = [("aquecimento", t0, t0 + W)]
    intervention = man.get("intervention", "none")
    if intervention == "none":
        phases.append(("util", t0 + W, t0 + W + P))
        end = t0 + W + P
    else:
        s0, s1 = ev.get("stress_start"), ev.get("stress_end")
        if s0 is None or s1 is None:
            print("ERRO: events-server.csv sem stress_start/stress_end", file=sys.stderr)
            return 2
        end = min(s1 + P, k6_end)
        phases += [("antes", t0 + W, s0), ("durante", s0, s1), ("depois", s1, end)]

    rows = [phase_stats(n, a, b, attempts, oks, dropped, probe) for (n, a, b) in phases]
    out = os.path.join(d, "analysis")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "phases.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["run_id", "cenario", "repeticao"] + list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({"run_id": man["run_id"], "cenario": man["scenario"], "repeticao": man["repetition"], **r})
    win = windows(t0, end, attempts, oks)
    with open(os.path.join(out, "windows.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(win[0].keys()))
        w.writeheader()
        w.writerows(win)

    summary = {"run_id": man["run_id"], "script": VERSION, "metodo_percentil": "posto mais proximo",
               "fases": rows, "k6_total_tentativas": len(attempts)}
    if intervention != "none":
        by = {r["fase"]: r for r in rows}
        pb, pd_, pa = by["antes"]["p95_ms"], by["durante"]["p95_ms"], by["depois"]["p95_ms"]
        rec_s, rec_status = recovery(ev["stress_end"], end, attempts, oks, pb, args.recovery_factor)
        summary.update({
            "intervencao": intervention,
            "stress_start_utc_notebook": iso(ev["stress_start"]),
            "stress_end_utc_notebook": iso(ev["stress_end"]),
            "delta_p95_ms": None if pb is None or pd_ is None else round(pd_ - pb, 3),
            "razao_p95_depois_antes": None if not pb or pa is None else round(pa / pb, 3),
            "recuperacao_s": rec_s, "recuperacao_status": rec_status,
            "recuperacao_regra": f"janela 30 s, passo 5 s, P95 <= {args.recovery_factor} x P95(antes), "
                                 "zero falhas, mantida por 60 s",
        })
    json.dump(summary, open(os.path.join(out, "summary.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    for r in rows:
        print(f"{r['fase']:<12} N={r['respostas_corretas']:>6} P95={r['p95_ms']} ms P99={r['p99_ms']} ms "
              f"erro={r['erro_composto_pct']}% vazao_ok={r['vazao_sucesso_rps']} rps "
              f"disp={r['disponibilidade_pct']}% cob={r['cobertura_pct']}% dropped={r['dropped_iterations']}")
    if intervention != "none":
        print(f"Delta P95={summary['delta_p95_ms']} ms  recuperacao={summary['recuperacao_status']} "
              f"({summary['recuperacao_s']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
