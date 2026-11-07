#!/usr/bin/env bash
# scripts/run_ramp.sh - executa a RAMPA de capacidade (piloto da Etapa 6) e gera a Figura C10.
# Roda no WSL do notebook, a partir da raiz do repositorio (como run_scenario.sh).
#
# Uso:  scripts/run_ramp.sh [STEPS] [STEP_S]
#   ex.: scripts/run_ramp.sh                      # 10,20,40,60,80,100,120 RPS, 60 s por degrau
#        scripts/run_ramp.sh 10,20,30,40,50,60 60
# Interromper com seguranca: Ctrl+C.
#
# Grava em runs/pilot/RAMP-<UTC>/: manifest.json, k6-raw.json, k6-summary.json,
# notebook-vmstat.txt (CPU do gerador, horario UTC), ping.txt, clock-offset.csv,
# server/ (series exportadas do Prometheus, inclusive CPU do servidor),
# analysis/ramp-steps.csv e checksums.sha256. A figura vai para results/charts/C10-rampa.png.
set -euo pipefail

STEPS="${1:-${STEPS:-10,20,40,60,80,100,120}}"
STEP_S="${2:-${STEP_S:-60}}"
[[ "$STEPS" =~ ^[0-9]+(,[0-9]+)*$ && "$STEP_S" =~ ^[0-9]+$ ]] || { echo "STEPS ou STEP_S invalidos"; exit 2; }
COMMON_ENV="${COMMON_ENV:-experiments/scenarios/common.env}"
[[ -f "$COMMON_ENV" ]] || { echo "execute na raiz do repositorio; ${COMMON_ENV} inexistente"; exit 2; }
set -a
# shellcheck disable=SC1090
source "$COMMON_ENV"
set +a
RAMP_PRE_VUS="${RAMP_PRE_VUS:-100}"
RAMP_MAX_VUS="${RAMP_MAX_VUS:-300}"

ts()    { python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).isoformat(timespec="microseconds"))'; }
stamp() { python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))'; }
RUN_ID="RAMP-$(stamp)"
OUT="${RUNS_DIR}/pilot/${RUN_ID}"
mkdir -p "$OUT"
log() { echo "[$(ts)] $*" | tee -a "$OUT/orchestrator.log"; }
N_STEPS=$(tr ',' '\n' <<<"$STEPS" | wc -l)
TOTAL_S=$(( N_STEPS * (STEP_S + 10) ))
log "inicio RUN_ID=${RUN_ID} degraus=${STEPS} rps, ${STEP_S}s cada (+10 s de transicao); duracao ~${TOTAL_S}s"
abort() {
  log "INTERROMPIDA pelo operador (Ctrl+C)"
  kill "${K6_PID:-}" "${PING_PID:-}" "${VMSTAT_PID:-}" 2>/dev/null || true
  echo "INVALIDA: rampa interrompida pelo operador em $(ts)" >> "$OUT/notes.md"
  exit 130
}
trap abort INT TERM

# ---------- pre-condicoes ----------
git rev-parse HEAD > "$OUT/commit.txt"
git status --porcelain > "$OUT/git-status.txt"
scripts/clock_offset.sh "$SERVER" > "$OUT/clock-offset.csv"
OFFSET=$(python3 - "$OUT/clock-offset.csv" <<'PY'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1])))
print(min(rows, key=lambda r: float(r["rtt_s"]))["offset_s"])
PY
)
python3 -c "import sys; sys.exit(0 if abs(float('$OFFSET')) <= float('$MAX_CLOCK_OFFSET_S') else 1)" \
  || { log "ABORTADO: offset de relogio ${OFFSET}s acima do limite"; exit 1; }
ssh -o BatchMode=yes "$SERVER" "date -u; uptime; free -m; df -h /; (sensors 2>/dev/null || true); \
  docker ps --format '{{.Names}} {{.Status}}'; systemctl is-active tcc2-cpu tcc2-mem 2>/dev/null || true" \
  > "$OUT/server-precheck.txt" 2>&1
if grep -qx active "$OUT/server-precheck.txt"; then log "ABORTADO: estressor ativo no servidor"; exit 1; fi

# ---------- manifesto ----------
export RUN_ID STEPS STEP_S OFFSET TOTAL_S RAMP_PRE_VUS RAMP_MAX_VUS
python3 - "$OUT/manifest.json" <<'PY'
import json, os, sys, platform, subprocess
e = os.environ
def sh(c):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as x: return f"erro: {x}"
m = {"run_id": e["RUN_ID"], "scenario": "RAMP", "repetition": "r01", "kind": "pilot",
     "protocol_version": e["PROTOCOL_VERSION"],
     "commit": open(os.path.join(os.path.dirname(sys.argv[1]), "commit.txt")).read().strip(),
     "base_url": e["BASE_URL"], "n": int(e["N"]), "expected_digest": e["EXPECTED_DIGEST"],
     "steps": [int(s) for s in e["STEPS"].split(",")], "step_s": int(e["STEP_S"]), "transition_s": 10,
     "total_s": int(e["TOTAL_S"]), "http_timeout": e["HTTP_TIMEOUT"],
     "pre_vus": int(e["RAMP_PRE_VUS"]), "max_vus": int(e["RAMP_MAX_VUS"]), "clock_offset_s": float(e["OFFSET"]),
     "generator": {"host": platform.node(), "kernel": platform.release(), "k6": sh("k6 version"),
                   "python": platform.python_version()}}
json.dump(m, open(sys.argv[1], "w"), indent=2, ensure_ascii=False)
PY

# ---------- medidores e carga ----------
HOST=$(python3 -c "import urllib.parse; print(urllib.parse.urlsplit('$BASE_URL').hostname)")
ping -D -i 1 "$HOST" > "$OUT/ping.txt" 2>&1 & PING_PID=$!
TZ=UTC vmstat -n -t 5 > "$OUT/notebook-vmstat.txt" 2>&1 & VMSTAT_PID=$!
sleep 2
K6_START=$(ts)
log "k6 (rampa) inicio ${K6_START}"
K6_EXIT=0
RUN_ID="$RUN_ID" STEPS="$STEPS" STEP_S="$STEP_S" PRE_VUS="$RAMP_PRE_VUS" MAX_VUS="$RAMP_MAX_VUS" \
  k6 run --quiet --out "json=$OUT/k6-raw.json" --summary-export "$OUT/k6-summary.json" \
  experiments/k6/ramp.js > "$OUT/k6-console.txt" 2>&1 & K6_PID=$!
wait "$K6_PID" || K6_EXIT=$?
echo "$K6_EXIT" > "$OUT/k6-exit-code.txt"
log "k6 terminou exit=${K6_EXIT} (na rampa, thresholds/erros perto do joelho sao esperados)"
sleep 20
kill "$PING_PID" "$VMSTAT_PID" 2>/dev/null || true
END_TS=$(ts)

# ---------- exportacao do servidor (CPU do servidor por degrau) ----------
EXP_START=$(python3 -c "import datetime as d; t=d.datetime.fromisoformat('$K6_START')+d.timedelta(seconds=float('$OFFSET')-60); print(t.isoformat())")
EXP_END=$(python3 -c "import datetime as d; t=d.datetime.fromisoformat('$END_TS')+d.timedelta(seconds=float('$OFFSET')+30); print(t.isoformat())")
EXPORT_RC=0
ssh -o BatchMode=yes "$SERVER" "python3 ${SERVER_REPO}/scripts/export_run.py --run-id ${RUN_ID} --start ${EXP_START} --end ${EXP_END} --project ${COMPOSE_PROJECT:-tcc2}" \
  > "$OUT/export.log" 2>&1 || EXPORT_RC=$?
scp -q -r "$SERVER:tcc2-exports/${RUN_ID}" "$OUT/server" || log "AVISO: falha no scp"
if [[ "$EXPORT_RC" -ne 0 ]]; then
  log "AVISO: exportacao incompleta (rc=$EXPORT_RC); a figura pode sair sem a CPU do servidor"
fi

python3 - "$OUT/manifest.json" "$K6_START" "$END_TS" "$K6_EXIT" <<'PY'
import json, sys
p, k6s, end, k6x = sys.argv[1:5]
m = json.load(open(p))
m.update({"k6_start_utc": k6s, "end_utc": end, "k6_exit_code": int(k6x)})
json.dump(m, open(p, "w"), indent=2, ensure_ascii=False)
PY
cat > "$OUT/notes.md" <<EOF
# Notas da rampa ${RUN_ID}
- Joelho escolhido (registrar em protocol-v1.md): PENDENTE
- Gerador saturou (CPU do gerador alta ou dropped_iterations antes do servidor saturar)? PENDENTE
- Incidentes / observacoes do operador:
EOF
( cd "$OUT" && find . -type f ! -name checksums.sha256 ! -path './analysis/*' ! -name 'notes.md' -print0 \
    | sort -z | xargs -0 sha256sum > checksums.sha256 )
python3 scripts/analyze_ramp.py "$OUT" | tee "$OUT/analysis-ramp.txt"
python3 scripts/fig_rampa.py "$OUT" --saida "results/charts/C10-rampa-${RUN_ID}.png" || log "AVISO: figura nao gerada"
log "fim. Pasta: ${OUT}"
echo ">> Escolha o joelho, registre em protocol-v1.md e preencha ${OUT}/notes.md."
