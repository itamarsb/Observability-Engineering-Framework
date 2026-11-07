#!/usr/bin/env python3
"""Executor da campanha: roda os 3 blocos (C0-C6 em ordem alternada) chamando
scripts/run_scenario.sh <CENARIO> <rNN> campaign, uma execucao por vez.

Antes de cada execucao:
  1. respeita o intervalo minimo desde o fim da anterior (INTERVALO_S);
  2. confere o estado estavel do servidor na ultima janela de ESTAVEL_S segundos, via SSH
     (CPU em repouso, MemAvailable, disco livre, temperatura, alvos "up" e estressores parados).
Depois de cada execucao:
  - execucao invalidada automaticamente pelo run_scenario.sh (falha tecnica) e refeita no fim
    do bloco, ate REFAZER_FALHAS vezes; a pasta invalida e PRESERVADA (nunca apagada);
  - ABORTADO por pre-condicao (relogio, git, estressor ativo) ou Ctrl+C: a campanha PARA.
Retomada: rodar de novo o mesmo comando. Execucoes ja feitas (VALIDA ou PENDENTE de revisao)
sao puladas; a classificacao final em notes.md continua sendo decisao do operador.
Parada segura: criar o arquivo runs/campaign-logs/PARAR (termina a execucao atual e para).

Uso (no WSL do notebook, na raiz do repositorio):
  python3 scripts/run_campaign.py --dry-run          # plano, estimativa e verificacoes, sem carga
  python3 scripts/run_campaign.py                    # campanha completa (ou retomada)
  python3 scripts/run_campaign.py --blocos 2 --cenarios C4,C6
Registros: runs/campaign-logs/campanha-<UTC>.log e campanha-<UTC>-estado.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

VERSION = "run_campaign/1.0"
GIB = 2**30


# ---------------- configuracao ----------------
def ler_env(caminho: str) -> dict:
    out = {}
    with open(caminho, encoding="utf-8") as fh:
        linhas = fh.readlines()
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        v = v.strip()
        if v.startswith('"'):
            v = v[1:v.index('"', 1)] if '"' in v[1:] else v[1:]
        else:
            v = v.split("#", 1)[0].strip()
        out[k.strip()] = v
    return out


def agora() -> float:
    return time.time()


def utc(t: float | None = None) -> str:
    return dt.datetime.fromtimestamp(t or agora(), dt.timezone.utc).isoformat(timespec="seconds")


class Registro:
    def __init__(self, pasta: str):
        os.makedirs(pasta, exist_ok=True)
        st = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.log_path = os.path.join(pasta, f"campanha-{st}.log")
        self.csv_path = os.path.join(pasta, f"campanha-{st}-estado.csv")
        self.linhas: list[dict] = []

    def __call__(self, msg: str) -> None:
        linha = f"[{utc()}] {msg}"
        print(linha, flush=True)
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(linha + "\n")

    def evento(self, **kv) -> None:
        self.linhas.append(kv)
        campos = list(dict.fromkeys(k for li in self.linhas for k in li))
        with open(self.csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=campos)
            w.writeheader()
            w.writerows(self.linhas)


# ---------------- estado das execucoes ----------------
def tentativas(runs_campaign: str, cen: str, rep: str) -> list[tuple[str, str]]:
    """[(pasta, situacao)] das execucoes ja existentes para cenario/repeticao, em ordem de criacao.
    situacao: VALIDA, PENDENTE, INVALIDA, INVALIDA (auto) ou INCOMPLETA (sem notes.md)."""
    out = []
    for p in sorted(glob.glob(os.path.join(runs_campaign, f"{cen}-{rep}-*"))):
        if not os.path.isdir(p):
            continue
        notes = os.path.join(p, "notes.md")
        if not os.path.exists(notes):
            out.append((p, "INCOMPLETA"))
            continue
        with open(notes, encoding="utf-8") as fh:
            txt = fh.read()
        st = re.findall(r"(?im)^\s*-\s*Classificacao final:\s*(VALIDA|INVALIDA|PENDENTE)\s*$", txt)
        if "INVALIDA:" in txt:
            out.append((p, "INVALIDA (auto)"))
        else:
            out.append((p, st[0] if len(st) == 1 else "PENDENTE"))
    return out


def concluida(sit: list[tuple[str, str]]) -> bool:
    return any(s in ("VALIDA", "PENDENTE") for _, s in sit)


# ---------------- estabilidade do servidor ----------------
CONSULTAS = {
    "cpu_max_pct": ('max_over_time((100 * (1 - avg(rate(node_cpu_seconds_total{{job="node",mode="idle"}}[30s]))))'
                    '[{j}s:5s])'),
    "mem_min_bytes": 'min(min_over_time(node_memory_MemAvailable_bytes{{job="node"}}[{j}s]))',
    "temp_max_c": 'max(max_over_time(node_hwmon_temp_celsius{{job="node"}}[{j}s]))',
    "alvos_min_up": 'min(min_over_time(up[{j}s]))',
}


def script_remoto(janela_s: int) -> str:
    linhas = ["set -u"]
    for nome, q in CONSULTAS.items():
        linhas.append(f"printf '{nome}\\t'; curl -s --max-time 5 -G 'http://127.0.0.1:9090/api/v1/query' "
                      f"--data-urlencode 'query={q.format(j=janela_s)}'; echo")
    linhas.append("printf 'disco_livre_bytes\\t'; df -B1 --output=avail / | tail -1")
    linhas.append("printf 'estressores\\t'; "
                  "(systemctl is-active tcc2-cpu tcc2-mem 2>/dev/null || true) | tr '\\n' ' '; echo")
    return "\n".join(linhas) + "\n"


def avaliar_estabilidade(saida: str, cfg: dict) -> tuple[bool, list[str], dict]:
    """Interpreta a saida do script remoto. Devolve (estavel, motivos, valores)."""
    val: dict = {}
    for linha in saida.splitlines():
        if "\t" not in linha:
            continue
        nome, resto = linha.split("\t", 1)
        resto = resto.strip()
        if nome in CONSULTAS:
            try:
                res = json.loads(resto)["data"]["result"]
                val[nome] = float(res[0]["value"][1]) if res else None
            except (ValueError, KeyError, IndexError, TypeError):
                val[nome] = None
        elif nome == "disco_livre_bytes":
            val[nome] = float(resto) if resto.isdigit() else None
        elif nome == "estressores":
            val[nome] = resto
    motivos = []
    lim = lambda k, d: float(cfg[k]) if cfg.get(k, "") != "" else d  # noqa: E731
    if val.get("cpu_max_pct") is None:
        motivos.append("CPU do servidor sem dados no Prometheus")
    elif val["cpu_max_pct"] > lim("CPU_REPOUSO_MAX_PCT", 25):
        motivos.append(f"CPU em repouso {val['cpu_max_pct']:.1f}% > {lim('CPU_REPOUSO_MAX_PCT', 25):g}%")
    if val.get("mem_min_bytes") is None:
        motivos.append("MemAvailable sem dados")
    elif val["mem_min_bytes"] / GIB < lim("MEM_DISPONIVEL_MIN_GIB", 2):
        motivos.append(f"MemAvailable {val['mem_min_bytes'] / GIB:.2f} GiB < {lim('MEM_DISPONIVEL_MIN_GIB', 2):g} GiB")
    if val.get("disco_livre_bytes") is None:
        motivos.append("disco livre desconhecido")
    elif val["disco_livre_bytes"] / GIB < lim("DISCO_LIVRE_MIN_GIB", 20):
        motivos.append(f"disco livre {val['disco_livre_bytes'] / GIB:.1f} GiB < {lim('DISCO_LIVRE_MIN_GIB', 20):g} GiB")
    if cfg.get("TEMP_MAX_C", "") != "":
        if val.get("temp_max_c") is None:
            motivos.append("temperatura sem dados")
        elif val["temp_max_c"] >= float(cfg["TEMP_MAX_C"]):
            motivos.append(f"temperatura {val['temp_max_c']:.1f} C >= {cfg['TEMP_MAX_C']} C")
    if val.get("alvos_min_up") is None or val["alvos_min_up"] < 1:
        motivos.append("algum alvo do Prometheus caiu na janela (up < 1)")
    if "active" in (val.get("estressores") or "").split():
        motivos.append("estressor tcc2-cpu/tcc2-mem ativo")
    return not motivos, motivos, val


def checar_servidor(servidor: str, cfg: dict) -> tuple[bool, list[str], dict]:
    janela = int(cfg.get("ESTAVEL_S") or 60)
    try:
        p = subprocess.run(["ssh", "-o", "BatchMode=yes", servidor, "bash", "-s"], input=script_remoto(janela),
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, [f"SSH falhou: {exc!r}"], {}
    if p.returncode != 0 and not p.stdout:
        return False, [f"SSH rc={p.returncode}: {p.stderr.strip()[:200]}"], {}
    return avaliar_estabilidade(p.stdout, cfg)


# ---------------- execucao ----------------
def esperar(seg: float, log: Registro, parar: str, motivo: str) -> bool:
    """Espera 'seg' segundos; devolve False se o arquivo PARAR aparecer."""
    if seg <= 0:
        return not os.path.exists(parar)
    log(f"aguardando {seg:.0f} s ({motivo})")
    fim = agora() + seg
    while agora() < fim:
        if os.path.exists(parar):
            return False
        time.sleep(min(5.0, max(0.0, fim - agora())))
    return not os.path.exists(parar)


def rodar(executor: str, cen: str, rep: str, common: str, log: Registro) -> int:
    log(f">>> executando {cen} {rep} ({executor})")
    # o mesmo common.env do executor vale para o run_scenario.sh (ex.: common-repro.env)
    env = {**os.environ, "COMMON_ENV": common}
    # sem bit de execucao (ex.: arquivo copiado do Windows), chama pelo bash
    cmd = [executor] if os.access(executor, os.X_OK) else ["bash", executor]
    try:
        proc = subprocess.Popen(cmd + [cen, rep, "campaign"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, env=env)
    except OSError as exc:
        log(f"ERRO ao iniciar {executor}: {exc}")
        return 127
    try:
        for linha in proc.stdout:
            print(linha, end="", flush=True)
            with open(log.log_path, "a", encoding="utf-8") as fh:
                fh.write("    | " + linha)
        return proc.wait()
    except KeyboardInterrupt:
        log("Ctrl+C recebido: aguardando o run_scenario.sh encerrar com seguranca")
        try:
            return proc.wait(timeout=60) or 130
        except subprocess.TimeoutExpired:
            proc.terminate()
            return 130


def duracao_estimada(cen: str, common: dict, cenarios_dir: str) -> float:
    W, P = float(common.get("WARMUP_S", 60)), float(common.get("PHASE_S", 180))
    env = ler_env(os.path.join(cenarios_dir, f"{cen}.env"))
    if env.get("INTERVENTION", "none") == "none":
        return W + P + 90
    return W + 2 * P + float(env.get("INTERVENTION_DURATION_S") or P) + 90


def main() -> int:
    ap = argparse.ArgumentParser(description="Executor da campanha do TCC2")
    ap.add_argument("--config", default="experiments/scenarios/campaign.env")
    ap.add_argument("--common", default=os.environ.get("COMMON_ENV", "experiments/scenarios/common.env"))
    ap.add_argument("--blocos", default="1,2,3")
    ap.add_argument("--cenarios", help="limita aos cenarios listados, ex.: C0,C4")
    ap.add_argument("--dry-run", action="store_true", help="mostra plano e verifica pre-requisitos, sem carga")
    ap.add_argument("--sem-servidor", action="store_true",
                    help="nao consulta o servidor (somente para testes do proprio executor)")
    ap.add_argument("--executor", default="scripts/run_scenario.sh")
    ap.add_argument("--intervalo", type=float, help="sobrepoe INTERVALO_S (s)")
    a = ap.parse_args()

    cfg, common = ler_env(a.config), ler_env(a.common)
    cen_dir = os.path.dirname(a.config) or "."
    runs_dir = common.get("RUNS_DIR", "runs")
    runs_campaign = os.path.join(runs_dir, "campaign")
    logs_dir = os.path.join(runs_dir, "campaign-logs")
    parar = os.path.join(logs_dir, "PARAR")
    intervalo = a.intervalo if a.intervalo is not None else float(cfg.get("INTERVALO_S") or 120)
    refazer = int(cfg.get("REFAZER_FALHAS") or 0)
    filtro = set(a.cenarios.split(",")) if a.cenarios else None
    blocos = []
    for b in [int(x) for x in a.blocos.split(",")]:
        ordem = cfg[f"BLOCO_{b}"].split()
        if cfg.get("INCLUIR_C7", "false").lower() == "true":
            ordem.append("C7")
        blocos.append((b, [c for c in ordem if filtro is None or c in filtro]))

    log = Registro(logs_dir)
    log(f"{VERSION} | blocos {a.blocos} | intervalo {intervalo:g} s | estavel {cfg.get('ESTAVEL_S', 60)} s"
        f" | refazer falhas ate {refazer}x | executor {a.executor}")
    total, pend = 0.0, 0
    for b, ordem in blocos:
        for cen in ordem:
            rep = f"r{b:02d}"
            sit = tentativas(runs_campaign, cen, rep)
            feito = concluida(sit)
            if not feito:
                pend += 1
                total += duracao_estimada(cen, common, cen_dir) + intervalo
            hist = ", ".join(f"{os.path.basename(p)}={s}" for p, s in sit) or "-"
            log(f"  bloco {b} {cen} {rep}: {'JA EXECUTADA' if feito else 'a executar'} | tentativas: {hist}")
    log(f"execucoes a fazer: {pend}; duracao estimada: {total / 3600:.1f} h (sem refazer falhas)")

    if a.dry_run:
        ok = True
        if not a.sem_servidor:
            if shutil.which("k6") is None:
                log("FALTA: k6 nao encontrado no PATH")
                ok = False
            sujo = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                                  capture_output=True, text=True).stdout.strip()
            if sujo:
                log("FALTA: arvore Git com alteracoes (run_scenario.sh aborta em 'campaign')")
                ok = False
            est, motivos, val = checar_servidor(common["SERVER"], cfg)
            log(f"servidor: {'ESTAVEL' if est else 'NAO ESTAVEL'} {val}" + (f" -> {motivos}" if motivos else ""))
            ok = ok and est
            if cfg.get("TEMP_MAX_C", "") == "":
                log("AVISO: TEMP_MAX_C vazio em campaign.env - temperatura nao sera verificada")
        log("dry-run concluido: " + ("pronto para a campanha" if ok else "corrija os itens acima"))
        return 0 if ok else 1

    try:
        return campanha(a, cfg, common, blocos, runs_campaign, parar, intervalo, refazer, log)
    except KeyboardInterrupt:
        log("Ctrl+C: campanha interrompida pelo operador (retomavel com o mesmo comando)")
        return 130


def campanha(a, cfg, common, blocos, runs_campaign, parar, intervalo, refazer, log) -> int:
    ultimo_fim = None
    for b, ordem in blocos:
        fila = [(cen, 0) for cen in ordem]
        while fila:
            cen, tentativa = fila.pop(0)
            rep = f"r{b:02d}"
            if os.path.exists(parar):
                log(f"arquivo {parar} encontrado: campanha interrompida pelo operador (retomavel)")
                return 0
            if concluida(tentativas(runs_campaign, cen, rep)):
                log(f"{cen} {rep}: ja executada - pulando")
                continue
            if ultimo_fim is not None:
                falta = intervalo - (agora() - ultimo_fim)
                if not esperar(falta, log, parar, "intervalo minimo entre execucoes"):
                    log("PARAR encontrado durante a espera: campanha interrompida (retomavel)")
                    return 0
            if not a.sem_servidor:
                est, motivos, val = False, [], {}
                for k in range(int(cfg.get("ESTAVEL_TENTATIVAS") or 10)):
                    est, motivos, val = checar_servidor(common["SERVER"], cfg)
                    if est:
                        break
                    log(f"servidor nao estavel ({'; '.join(motivos)}); nova verificacao em 30 s")
                    if not esperar(30, log, parar, "estado estavel"):
                        return 0
                if not est:
                    log(f"ABORTADA: servidor nao atingiu estado estavel: {motivos}")
                    log.evento(bloco=b, cenario=cen, repeticao=rep, tentativa=tentativa + 1, inicio_utc=utc(),
                               rc="", situacao="nao iniciada: servidor instavel", pasta="")
                    return 3
                log(f"servidor estavel: {val}")
            inicio = utc()
            antes = {p for p, _ in tentativas(runs_campaign, cen, rep)}
            rc = rodar(a.executor, cen, rep, a.common, log)
            ultimo_fim = agora()
            novas = [(p, s) for p, s in tentativas(runs_campaign, cen, rep) if p not in antes]
            pasta, sit = novas[-1] if novas else ("", "sem pasta")
            log.evento(bloco=b, cenario=cen, repeticao=rep, tentativa=tentativa + 1, inicio_utc=inicio,
                       fim_utc=utc(ultimo_fim), rc=rc, situacao=sit, pasta=pasta)
            if rc == 130:
                log("interrompida pelo operador (Ctrl+C): campanha parada (retomavel)")
                return 130
            if rc != 0:
                log(f"run_scenario.sh terminou com rc={rc} (pre-condicao/aborto): campanha parada. "
                    "Corrija a causa (ver orchestrator.log da pasta) e rode de novo para retomar.")
                return 4
            if sit == "INVALIDA (auto)":
                if tentativa < refazer:
                    log(f"{cen} {rep}: invalida por falha tecnica; nova tentativa no fim do bloco {b}")
                    fila.append((cen, tentativa + 1))
                else:
                    log(f"{cen} {rep}: invalida por falha tecnica e sem novas tentativas; revisar depois")
            else:
                log(f"{cen} {rep}: concluida ({sit}); a classificacao sai em scripts/revisar_execucoes.py")
    log("campanha concluida. Proximos passos: python3 scripts/revisar_execucoes.py --aplicar "
        "e depois python3 scripts/gerar_resultados.py (ver results/README.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
