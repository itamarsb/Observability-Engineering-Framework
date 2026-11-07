"""Leitura dos dados brutos de UMA execucao para figuras e tabelas (biblioteca padrao).

Le apenas arquivos ja gravados pelo orquestrador; nao consulta o servidor.
  manifest.json, analysis/phases.csv     limites das fases (relogio do notebook)
  k6-raw.json                            latencia vista pelo cliente (fonte primaria dos SLIs)
  server/prom-<nome>.json                series do Prometheus (step 5 s)
  server/loki-api.jsonl | server/api.log evento request_completed (duracao interna da API)
  server/nginx.log                       request_time e upstream_response_time do NGINX
  server/containers-state.json, server/kernel.log   OOM e reinicios
  notebook-vmstat.txt                    CPU do gerador (requer "vmstat -t" em UTC)

Relogios: t_notebook = t_servidor - clock_offset_s (mesma regra do analyze_run.py).
Todas as series sao devolvidas em tempo RELATIVO ao inicio do k6 (s).
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_run import load_k6, nearest_rank, parse_ts  # noqa: E402

AMOSTRAS_MIN_P95 = 20  # menos que isso: P95 da janela fica indefinido (lacuna no grafico)
OOM_RE = re.compile(r"out of memory|oom-kill|oom_reaper|killed process", re.I)


# ---------- leitura de arquivos (sempre fechando o arquivo) ----------
def ler_json(caminho: str):
    with open(caminho, encoding="utf-8") as fh:
        return json.load(fh)


def ler_csv(caminho: str) -> list[dict]:
    with open(caminho, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def ler_texto(caminho: str) -> str:
    with open(caminho, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def ler_linhas(caminho: str) -> list[str]:
    with open(caminho, encoding="utf-8", errors="replace") as fh:
        return fh.readlines()


class Execucao:
    def __init__(self, pasta: str):
        self.pasta = pasta
        self.manifest = ler_json(self._p("manifest.json"))
        self.t0 = parse_ts(self.manifest["k6_start_utc"])
        self.offset = float(self.manifest.get("clock_offset_s") or 0.0)
        self.run_id = self.manifest["run_id"]
        self.cenario = self.manifest.get("scenario", "")
        self.repeticao = self.manifest.get("repetition", "")
        self.fases = self._ler_fases()
        self.lidos: list[str] = [self._p("manifest.json")]
        self._k6 = None

    # ---------- utilitarios ----------
    def _p(self, *partes: str) -> str:
        return os.path.join(self.pasta, *partes)

    def _marcar(self, caminho: str) -> None:
        if os.path.isfile(caminho) and caminho not in self.lidos:
            self.lidos.append(caminho)

    @property
    def sintetica(self) -> bool:
        m = self.manifest
        return bool(m.get("synthetic")) or m.get("kind") == "synthetic" or self.run_id.startswith("SINT")

    def _ler_fases(self) -> list[tuple[str, float, float]]:
        p = self._p("analysis", "phases.csv")
        if not os.path.exists(p):
            raise FileNotFoundError(f"{p} ausente: rode antes  python3 scripts/analyze_run.py {self.pasta}")
        out = []
        for r in ler_csv(p):
            out.append((r["fase"], parse_ts(r["inicio_utc"]) - self.t0, parse_ts(r["fim_utc"]) - self.t0))
        return out

    def fase(self, nome: str) -> tuple[float, float] | None:
        for n, a, b in self.fases:
            if n == nome:
                return a, b
        return None

    @property
    def fim_rel(self) -> float:
        return max(b for _, _, b in self.fases)

    def eventos(self) -> dict:
        """stress_start/stress_end em tempo relativo + campo detail (ex.: 'netem delay=100ms')."""
        p = self._p("events-server.csv")
        ev, det = {}, {}
        if os.path.exists(p):
            self._marcar(p)
            for r in ler_csv(p):
                ev[r["event"]] = parse_ts(r["timestamp_utc"]) - self.offset - self.t0
                det[r["event"]] = r.get("detail", "")
        return {"t": ev, "detalhe": det}

    # ---------- cliente (k6) ----------
    def k6(self):
        if self._k6 is None:
            p = self._p("k6-raw.json")
            self._marcar(p)
            att, oks, drp = load_k6(p)
            self._k6 = ([(t - self.t0, f) for t, f in att], [(t - self.t0, ms) for t, ms in oks],
                        [(t - self.t0, n) for t, n in drp])
        return self._k6

    def serie_cliente(self, janela: float) -> dict:
        _att, oks, _drp = self.k6()
        return janelas_p95(oks, 0.0, self.fim_rel, janela)

    # ---------- servidor ----------
    def prom(self, nome: str) -> list[tuple[float, float]]:
        """Primeira serie de server/prom-<nome>.json; lista vazia se ausente ou sem amostras."""
        p = self._p("server", f"prom-{nome}.json")
        if not os.path.exists(p):
            return []
        self._marcar(p)
        res = ler_json(p).get("data", {}).get("result", [])
        if not res:
            return []
        out = []
        for ts, val in res[0].get("values", []):
            try:
                v = float(val)
            except ValueError:
                continue
            if v == v:  # descarta NaN
                out.append((float(ts) - self.offset - self.t0, v))
        return out

    def duracoes_internas(self) -> tuple[list[tuple[float, float]], str]:
        """(t_rel, duration_ms) do evento request_completed em /work deste run_id.
        Fonte preferencial: Loki (exportado); alternativa: stdout da API (api.log)."""
        out: list[tuple[float, float]] = []
        p = self._p("server", "loki-api.jsonl")
        if os.path.exists(p):
            for linha in ler_linhas(p):
                if not linha.strip():
                    continue
                j = json.loads(linha)
                attrs = {**(j.get("fields") or {}), **(j.get("structured_metadata") or {})}
                corpo = j.get("line", "")
                if corpo.startswith("{"):
                    try:
                        attrs = {**json.loads(corpo), **attrs}
                    except ValueError:
                        pass
                rec = _request_completed(attrs, corpo, self.run_id)
                if rec is not None:
                    out.append((int(j["ts_ns"]) / 1e9 - self.offset - self.t0, rec))
            if out:
                self._marcar(p)
                return out, "Loki (request_completed)"
        p = self._p("server", "api.log")
        if os.path.exists(p):
            for linha in ler_linhas(p):
                linha = linha.strip()
                if " {" not in linha:
                    continue
                ts, js = linha.split(" ", 1)
                try:
                    attrs = json.loads(js)
                    t = parse_ts(ts)
                except ValueError:
                    continue
                rec = _request_completed(attrs, attrs.get("event", ""), self.run_id)
                if rec is not None:
                    out.append((t - self.offset - self.t0, rec))
            if out:
                self._marcar(p)
                return out, "log da API (stdout)"
        return [], "indisponivel"

    def nginx(self) -> list[tuple[float, float, float | None, int]]:
        """(t_rel, request_time_ms, upstream_ms|None, status) das linhas deste run_id."""
        p = self._p("server", "nginx.log")
        out = []
        if not os.path.exists(p):
            return out
        for linha in ler_linhas(p):
            linha = linha.strip()
            if " {" not in linha:
                continue
            ts, js = linha.split(" ", 1)
            try:
                j = json.loads(js)
                if not str(j.get("run_id", "")).startswith(self.run_id):
                    continue
                up = str(j.get("upstream_response_time", "-"))
                out.append((parse_ts(ts) - self.offset - self.t0, float(j["request_time"]) * 1000,
                            None if up in ("-", "") else float(up.split(",")[-1]) * 1000, int(j["status"])))
            except (ValueError, KeyError):
                continue
        if out:
            self._marcar(p)
        return out

    def oom(self) -> dict:
        """Eventos OOM do kernel (t_rel, texto) e conteineres com OOMKilled."""
        eventos = []
        p = self._p("server", "kernel.log")
        if os.path.exists(p):
            self._marcar(p)
            for linha in ler_linhas(p):
                if OOM_RE.search(linha):
                    try:
                        t = parse_ts(linha.split(" ", 1)[0]) - self.offset - self.t0
                    except ValueError:
                        t = None
                    eventos.append((t, linha.strip()))
        mortos = []
        p = self._p("server", "containers-state.json")
        if os.path.exists(p):
            self._marcar(p)
            mortos = [c["name"] for c in ler_json(p) if c.get("oom_killed")]
        return {"kernel": eventos, "conteineres": mortos, "fonte_disponivel": os.path.exists(p)}

    def cpu_gerador(self) -> list[tuple[float, float]]:
        """CPU ocupada do gerador (100 - id) a partir de notebook-vmstat.txt gravado com -t em UTC."""
        p = self._p("notebook-vmstat.txt")
        if not os.path.exists(p):
            return []
        pontos = ler_vmstat(p)
        if pontos:
            self._marcar(p)
        return [(t - self.t0, v) for t, v in pontos]

    # ---------- resumos por fase ----------
    def contexto_por_fase(self) -> dict:
        """Indicadores auxiliares por fase (descritivos; os SLIs vem do analyze_run.py)."""
        cpu = self.prom("cpu_host_pct")
        mem = self.prom("mem_available_bytes")
        swap = self.prom("swap_used_bytes")
        internos, fonte_int = self.duracoes_internas()
        ngx = self.nginx()
        oom = self.oom()
        gen = self.cpu_gerador()
        res = {}
        for nome, a, b in self.fases:
            dentro = lambda serie: [v for t, v in serie if a <= t < b]  # noqa: E731
            c, m, s, g = dentro(cpu), dentro(mem), dentro(swap), dentro(gen)
            it = dentro(internos)
            up = [u for t, _rt, u, _st in ngx if a <= t < b and u is not None]
            rt = [r for t, r, _u, _st in ngx if a <= t < b]
            res[nome] = {
                "cpu_servidor_media_pct": _r(statistics.fmean(c)) if c else None,
                "cpu_servidor_max_pct": _r(max(c)) if c else None,
                "mem_disponivel_min_gib": _r(min(m) / 2**30, 2) if m else None,
                "swap_max_gib": _r(max(s) / 2**30, 3) if s else None,
                "p95_interno_ms": _r(nearest_rank(it, 0.95)) if len(it) >= AMOSTRAS_MIN_P95 else None,
                "n_interno": len(it),
                "fonte_interno": fonte_int,
                "p95_upstream_nginx_ms": _r(nearest_rank(up, 0.95)) if len(up) >= AMOSTRAS_MIN_P95 else None,
                "p95_request_nginx_ms": _r(nearest_rank(rt, 0.95)) if len(rt) >= AMOSTRAS_MIN_P95 else None,
                "cpu_gerador_media_pct": _r(statistics.fmean(g)) if g else None,
                "cpu_gerador_max_pct": _r(max(g)) if g else None,
                "oom_kernel": sum(1 for t, _ in oom["kernel"] if t is not None and a <= t < b),
            }
        res["_oom_conteineres"] = oom["conteineres"]
        return res


def _request_completed(attrs: dict, corpo: str, run_id: str) -> float | None:
    evento = attrs.get("event") or corpo
    if evento != "request_completed":
        return None
    if not str(attrs.get("run_id", "")).startswith(run_id):
        return None
    rota = attrs.get("route")
    if rota not in (None, "", "/work"):
        return None
    try:
        return float(attrs["duration_ms"])
    except (KeyError, ValueError, TypeError):
        return None


def _r(x, nd=1):
    return None if x is None else round(x, nd)


def janelas_p95(registros: list[tuple[float, float]], a: float, b: float, passo: float) -> dict:
    """Agrupa (t_rel, ms) em janelas [a + k*passo, ...) completas; P95 indefinido com poucas amostras."""
    xs, p95, n = [], [], []
    regs = sorted(registros)
    i = 0
    t = a
    while t + passo <= b + 1e-9:
        u = t + passo
        while i < len(regs) and regs[i][0] < t:
            i += 1
        j = i
        vals = []
        while j < len(regs) and regs[j][0] < u:
            vals.append(regs[j][1])
            j += 1
        xs.append(t + passo / 2)
        n.append(len(vals))
        p95.append(nearest_rank(vals, 0.95) if len(vals) >= AMOSTRAS_MIN_P95 else None)
        t = u
    return {"t": xs, "p95": p95, "n": n}


def ler_vmstat(caminho: str) -> list[tuple[float, float]]:
    """Le 'vmstat -n -t <s>' (TZ=UTC). Descarta a 1a linha (media desde o boot).
    Sem coluna de horario (vmstat sem -t), devolve lista vazia: nao ha como alinhar."""
    cab = None
    pontos = []
    primeira = True
    for linha in ler_linhas(caminho):
        campos = linha.split()
        if not campos or campos[0].startswith("procs"):
            continue
        if campos[0] == "r":
            cab = campos
            continue
        if cab is None or "id" not in cab or not campos[0].isdigit():
            continue
        if primeira:
            primeira = False
            continue
        # Com -t o cabecalho termina no fuso ("UTC") e cada linha termina em "AAAA-MM-DD HH:MM:SS":
        # linha = (campos numericos do cabecalho) + data + hora = len(cab) + 1.
        if cab[-1] != "UTC" or len(campos) != len(cab) + 1:
            # sem -t, ou com fuso local: nao ha como alinhar com seguranca
            return []
        try:
            t = dt.datetime.strptime(f"{campos[-2]} {campos[-1]}", "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=dt.timezone.utc).timestamp()
            ocioso = float(campos[cab.index("id")])
        except ValueError:
            continue
        pontos.append((t, 100.0 - ocioso))
    return pontos
