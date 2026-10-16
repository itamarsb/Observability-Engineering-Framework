#!/usr/bin/env python3
"""Sonda externa de disponibilidade (roda no WSL do notebook, independente do k6).

Agenda as tentativas pelo relogio monotonico (t0 + i * intervalo), sem
"requisicao + sleep", para que a frequencia nao dependa da latencia.
Cada linha do CSV e gravada e descarregada imediatamente (flush).

Sucesso = HTTP 200 + JSON com n e digest esperados. Sem retries e sem redirects.
Oportunidade perdida (processo atrasado mais que --tolerance) = linha com
missed=true (dado ausente: nao e sucesso nem falha HTTP).

Uso:
  python3 scripts/probe.py --base-url http://10.10.10.1:8080 --n 20000 \
      --expected-digest <hex> --run-id C0-r01-... --out probe.csv \
      --interval 5 --timeout 2 --duration 300
Encerrar antes do fim: Ctrl+C ou SIGTERM (as linhas ja gravadas sao preservadas).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import http.client
import json
import signal
import sys
import time
import urllib.parse

VERSION = "probe/1.0"
HEADER = [
    "run_id", "seq", "scheduled_utc", "started_utc", "finished_utc", "duration_ms",
    "http_status", "body_ok", "success", "transport_error", "missed", "lateness_ms",
]
_stop = False


def _utc(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat(timespec="microseconds")


def _handle_stop(signum, frame):  # noqa: ARG001
    global _stop
    _stop = True


def one_attempt(host: str, port: int, path: str, timeout: float, run_id: str, n: int, digest: str):
    """Executa uma tentativa HTTP. Retorna (status, body_ok, transport_error)."""
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", path, headers={
            "X-Run-ID": f"{run_id}-probe",
            "User-Agent": "tcc2-probe/1",
            "Connection": "close",
        })
        resp = conn.getresponse()
        raw = resp.read()
        body_ok = False
        if resp.status == 200:
            try:
                data = json.loads(raw)
                body_ok = data.get("n") == n and data.get("digest") == digest
            except (ValueError, AttributeError):
                body_ok = False
        return resp.status, body_ok, ""
    except Exception as exc:  # timeout, conexao recusada, reset etc.
        return "", False, type(exc).__name__
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--expected-digest", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--duration", type=float, default=0.0, help="segundos; 0 = ate Ctrl+C/SIGTERM")
    ap.add_argument("--tolerance", type=float, default=1.0,
                    help="atraso maximo (s) para considerar a tentativa executada; acima disso = missed")
    args = ap.parse_args()

    u = urllib.parse.urlsplit(args.base_url)
    host, port = u.hostname, u.port or 80
    path = f"/work?n={args.n}"

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    t0_mono = time.monotonic()
    t0_wall = time.time()
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        fh.flush()
        i = 0
        while not _stop:
            sched_mono = t0_mono + i * args.interval
            if args.duration and (sched_mono - t0_mono) >= args.duration:
                break
            sched_wall = t0_wall + i * args.interval
            # dorme em fatias curtas ate o horario agendado (responde rapido ao SIGTERM)
            while not _stop and time.monotonic() < sched_mono:
                time.sleep(min(0.2, max(0.0, sched_mono - time.monotonic())))
            if _stop:
                break
            lateness = time.monotonic() - sched_mono
            if lateness > args.tolerance:
                # o processo atrasou (pausa, suspensao, CPU do notebook): oportunidade perdida
                w.writerow([args.run_id, i, _utc(sched_wall), "", "", "", "", "", "false", "", "true",
                            f"{lateness * 1000:.1f}"])
                fh.flush()
                i += 1
                continue
            started = time.time()
            m0 = time.monotonic()
            status, body_ok, terr = one_attempt(host, port, path, args.timeout, args.run_id, args.n, args.expected_digest)
            dur_ms = (time.monotonic() - m0) * 1000
            finished = time.time()
            success = status == 200 and body_ok
            w.writerow([
                args.run_id, i, _utc(sched_wall), _utc(started), _utc(finished), f"{dur_ms:.3f}",
                status, str(body_ok).lower(), str(success).lower(), terr, "false",
                f"{lateness * 1000:.1f}",
            ])
            fh.flush()
            i += 1
    print(f"{VERSION}: {i} oportunidades registradas em {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
