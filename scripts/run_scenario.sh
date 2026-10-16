#!/usr/bin/env bash
# scripts/run_scenario.sh - executa UMA execucao do protocolo (roda no WSL do notebook,
# a partir da raiz do repositorio clonado no WSL).
#
# Uso:  scripts/run_scenario.sh <CENARIO> <REPETICAO> [pilot|campaign|repro]
#   ex.: scripts/run_scenario.sh C0 r01 pilot
#        scripts/run_scenario.sh C4 r02 campaign
#        COMMON_ENV=experiments/scenarios/common-repro.env scripts/run_scenario.sh C0 r01 repro
# Interromper com seguranca: Ctrl+C (para k6, sonda e medidores e tenta parar estressores).
#
# O que faz, em ordem:
#   1. pre-condicoes: arvore Git limpa (campaign), offset de relogio, estado do servidor
#   2. manifest.json inicial
#   3. ping + sonda + recursos do notebook + k6 (em paralelo)
#   4. intervencao no inicio da fase "durante" (horarios gravados PELO SERVIDOR)
#   5. drenagem, parada dos medidores, exportacao no servidor e copia (scp)
#   6. manifest final, checksums.sha256 e analise preliminar
set -euo pipefail

SCEN="${1:?uso: run_scenario.sh C0 r01 [pilot|campaign]}"
REP="${2:?informe a repeticao, ex.: r01}"
KIND="${3:-campaign}"
[[ "$KIND" == pilot || "$KIND" == campaign || "$KIND" == repro ]] || { echo "tipo deve ser pilot, campaign ou repro"; exit 2; }
COMMON_ENV="${COMMON_ENV:-experiments/scenarios/common.env}"
[[ -f "$COMMON_ENV" && -f "experiments/scenarios/${SCEN}.env" ]] \
  || { echo "execute na raiz do repositorio; ${COMMON_ENV} ou cenario ${SCEN} inexistente"; exit 2; }
set -a
# shellcheck disable=SC1090
source "$COMMON_ENV"
# shellcheck disable=SC1090
source "experiments/scenarios/${SCEN}.env"
set +a
INTERVENTION_DURATION_S="${INTERVENTION_DURATION_S:-$PHASE_S}"

ts()    { python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).isoformat(timespec="microseconds"))'; }
stamp() { python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))'; }
RUN_ID="${SCEN}-${REP}-$(stamp)"
OUT="${RUNS_DIR}/${KIND}/${RUN_ID}"
mkdir -p "$OUT"
log() { echo "[$(ts)] $*" | tee -a "$OUT/orchestrator.log"; }
log "inicio RUN_ID=${RUN_ID} tipo=${KIND} protocolo=${PROTOCOL_VERSION}"
abort() {
  log "INTERROMPIDO pelo operador (Ctrl+C) - execucao deve ser marcada como INVALIDA"
  kill "${K6_PID:-}" "${PROBE_PID:-}" "${PING_PID:-}" "${VMSTAT_PID:-}" 2>/dev/null || true
  echo "INVALIDA: interrompida pelo operador em $(ts)" >> "$OUT/notes.md"
  echo ">> No servidor, confira/pare estressores:  sudo systemctl stop tcc2-cpu tcc2-mem  (netem: ver docs/runbooks/deployment.md)"
  exit 130
}
trap abort INT TERM

# ---------- 1. pre-condicoes ----------
if [[ "$KIND" == campaign ]]; then
  git diff --quiet && git diff --cached --quiet || { log "ABORTADO: arvore Git com alteracoes"; exit 1; }
fi
git rev-parse HEAD > "$OUT/commit.txt"
git status --porcelain > "$OUT/git-status.txt"
scripts/clock_offset.sh "$SERVER" > "$OUT/clock-offset.csv"
OFFSET=$(python3 - "$OUT/clock-offset.csv" <<'PY'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1])))
best = min(rows, key=lambda r: float(r["rtt_s"]))
print(best["offset_s"])
PY
)
python3 -c "import sys; sys.exit(0 if abs(float('$OFFSET')) <= float('$MAX_CLOCK_OFFSET_S') else 1)" \
  || { log "ABORTADO: offset de relogio ${OFFSET}s acima do limite"; exit 1; }
log "offset de relogio (servidor - notebook) = ${OFFSET} s"
SERVER_COMMIT=$(ssh -o BatchMode=yes "$SERVER" "git -C ${SERVER_REPO} rev-parse HEAD" 2>/dev/null || echo desconhecido)
echo "$SERVER_COMMIT" > "$OUT/server-commit.txt"
if [[ "$KIND" == campaign && "$SERVER_COMMIT" != "$(cat "$OUT/commit.txt")" ]]; then
  log "ABORTADO: commit do servidor (${SERVER_COMMIT}) difere do commit do notebook"; exit 1
fi
ssh -o BatchMode=yes "$SERVER" "date -u; uptime; free -m; df -h /; (sensors 2>/dev/null || true); \
  docker ps --format '{{.Names}} {{.Status}}'; \
  systemctl is-active tcc2-cpu tcc2-mem 2>/dev/null || true" > "$OUT/server-precheck.txt" 2>&1
if grep -qx active "$OUT/server-precheck.txt"; then log "ABORTADO: estressor ainda ativo no servidor"; exit 1; fi

if [[ "$INTERVENTION" == none ]]; then
  TOTAL_S=$((WARMUP_S + PHASE_S))
else
  TOTAL_S=$((WARMUP_S + PHASE_S + INTERVENTION_DURATION_S + PHASE_S))
fi

# ---------- 2. manifesto inicial ----------
export RUN_ID SCEN REP KIND OFFSET TOTAL_S INTERVENTION_DURATION_S
python3 - "$OUT/manifest.json" <<'PY'
import json, os, sys, platform, subprocess
e = os.environ
def sh(c):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as x: return f"erro: {x}"
m = {
  "run_id": e["RUN_ID"], "scenario": e["SCEN"], "scenario_name": e.get("SCENARIO_NAME"),
  "repetition": e["REP"], "kind": e["KIND"], "protocol_version": e["PROTOCOL_VERSION"],
  "commit": open(os.path.join(os.path.dirname(sys.argv[1]), "commit.txt")).read().strip(),
  "git_clean": os.path.getsize(os.path.join(os.path.dirname(sys.argv[1]), "git-status.txt")) == 0,
  "base_url": e["BASE_URL"], "n": int(e["N"]), "expected_digest": e["EXPECTED_DIGEST"],
  "rate_rps": float(e["RATE"]), "warmup_s": int(e["WARMUP_S"]), "phase_s": int(e["PHASE_S"]),
  "intervention": e["INTERVENTION"], "intervention_args": e.get("INTERVENTION_ARGS", ""),
  "intervention_duration_s": int(e["INTERVENTION_DURATION_S"]), "total_s": int(e["TOTAL_S"]),
  "http_timeout": e["HTTP_TIMEOUT"], "pre_vus": int(e["PRE_VUS"]), "max_vus": int(e["MAX_VUS"]),
  "probe_interval_s": float(e["PROBE_INTERVAL_S"]), "probe_timeout_s": float(e["PROBE_TIMEOUT_S"]),
  "clock_offset_s": float(e["OFFSET"]),
  "compose_project": e.get("COMPOSE_PROJECT", "tcc2"),
  "generator": {"host": platform.node(), "kernel": platform.release(),
                "k6": sh("k6 version"), "python": platform.python_version()},
}
json.dump(m, open(sys.argv[1], "w"), indent=2, ensure_ascii=False)
PY

# ---------- 3. medidores externos e carga ----------
HOST=$(python3 -c "import urllib.parse,sys; print(urllib.parse.urlsplit('$BASE_URL').hostname)")
ping -D -i 1 "$HOST" > "$OUT/ping.txt" 2>&1 & PING_PID=$!
vmstat -n 5 > "$OUT/notebook-vmstat.txt" 2>&1 & VMSTAT_PID=$!
python3 scripts/probe.py --base-url "$BASE_URL" --n "$N" --expected-digest "$EXPECTED_DIGEST" \
  --run-id "$RUN_ID" --out "$OUT/probe.csv" --interval "$PROBE_INTERVAL_S" \
  --timeout "$PROBE_TIMEOUT_S" --duration "$((TOTAL_S + 20))" 2> "$OUT/probe.log" & PROBE_PID=$!
sleep 2
K6_START=$(ts)
log "k6 inicio ${K6_START} taxa=${RATE} rps duracao=${TOTAL_S}s"
DURATION="${TOTAL_S}s" k6 run --quiet --out "json=$OUT/k6-raw.json" \
  --summary-export "$OUT/k6-summary.json" experiments/k6/work.js > "$OUT/k6-console.txt" 2>&1 & K6_PID=$!

# ---------- 4. intervencao ----------
INT_RC=""
if [[ "$INTERVENTION" != none ]]; then
  python3 - "$K6_START" "$((WARMUP_S + PHASE_S))" <<'PY'
import datetime as d, sys, time
t0 = d.datetime.fromisoformat(sys.argv[1]).timestamp()
wait = t0 + float(sys.argv[2]) - time.time()
if wait > 0: time.sleep(wait)
PY
  log "disparando intervencao ${INTERVENTION} (${INTERVENTION_DURATION_S}s ${INTERVENTION_ARGS})"
  # shellcheck disable=SC2086
  ssh -o BatchMode=yes "$SERVER" "sudo /usr/local/sbin/tcc2-${INTERVENTION}.sh ${INTERVENTION_DURATION_S} ${INTERVENTION_ARGS}" \
    > "$OUT/events-server.csv" 2> "$OUT/intervention.log" && INT_RC=0 || INT_RC=$?
  log "intervencao terminou rc=${INT_RC}"
fi
K6_EXIT=0; wait "$K6_PID" || K6_EXIT=$?
echo "$K6_EXIT" > "$OUT/k6-exit-code.txt"
log "k6 terminou exit=${K6_EXIT}"

# ---------- 5. drenagem, exportacao e copia ----------
sleep 20   # ultimas exportacoes de telemetria (batch + scrape) - fora da janela util
kill -TERM "$PROBE_PID" 2>/dev/null || true; wait "$PROBE_PID" 2>/dev/null || true
kill "$PING_PID" "$VMSTAT_PID" 2>/dev/null || true
END_TS=$(ts)
EXP_START=$(python3 -c "import datetime as d; t=d.datetime.fromisoformat('$K6_START')+d.timedelta(seconds=float('$OFFSET')-60); print(t.isoformat())")
EXP_END=$(python3 -c "import datetime as d; t=d.datetime.fromisoformat('$END_TS')+d.timedelta(seconds=float('$OFFSET')+30); print(t.isoformat())")
log "exportando no servidor ${EXP_START} -> ${EXP_END}"
ssh -o BatchMode=yes "$SERVER" "python3 ${SERVER_REPO}/scripts/export_run.py --run-id ${RUN_ID} --start ${EXP_START} --end ${EXP_END} --project ${COMPOSE_PROJECT:-tcc2}" \
  > "$OUT/export.log" 2>&1 || log "AVISO: exportacao retornou erro (ver export.log)"
scp -q -r "$SERVER:tcc2-exports/${RUN_ID}" "$OUT/server" || log "AVISO: falha no scp"

# ---------- 6. manifesto final, hashes e analise preliminar ----------
python3 - "$OUT/manifest.json" "$K6_START" "$END_TS" "$K6_EXIT" "${INT_RC}" <<'PY'
import json, sys
p, k6s, end, k6x, irc = sys.argv[1:6]
m = json.load(open(p))
m.update({"k6_start_utc": k6s, "end_utc": end, "k6_exit_code": int(k6x),
          "intervention_rc": None if irc == "" else int(irc)})
json.dump(m, open(p, "w"), indent=2, ensure_ascii=False)
PY
python3 scripts/analyze_run.py "$OUT" > "$OUT/analysis.txt" 2>&1 || log "AVISO: analise preliminar falhou"
cat > "$OUT/notes.md" <<EOF
# Notas da execucao ${RUN_ID}
- Validade da carga (k6 exit, dropped_iterations, CPU do notebook): PENDENTE
- Validade da sonda (cobertura = 100%?): PENDENTE
- Validade da telemetria (lacunas, reinicios, OOM, export-report): PENDENTE
- Intervencao aplicada como planejado? (events-server.csv, intervention.log): PENDENTE
- Incidentes / observacoes do operador:
EOF
log "fim. Pasta: ${OUT}"
# hashes por ULTIMO, so dos dados brutos e registros (derivados e notas ficam de fora).
# Conferir depois, DENTRO da pasta da execucao:  sha256sum -c checksums.sha256
( cd "$OUT" && find . -type f ! -name checksums.sha256 ! -path './analysis/*' ! -name 'analysis.txt' \
    ! -name 'notes.md' -print0 | sort -z | xargs -0 sha256sum > checksums.sha256 )
cat "$OUT/analysis.txt"
echo ">> Revise a execucao e preencha ${OUT}/notes.md (validade por dimensao e incidentes)."
