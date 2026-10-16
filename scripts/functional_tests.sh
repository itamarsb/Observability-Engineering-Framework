#!/usr/bin/env bash
# Testes funcionais da API ATRAVES do NGINX (Etapa 3). Roda no WSL do notebook.
# Uso: scripts/functional_tests.sh http://10.10.10.1:8080 <pasta_de_saida> [espera_controlled_error: 503|404]
# Gera: <pasta>/functional-tests.txt (relatorio PASSOU/FALHOU) + corpos e cabecalhos de cada chamada.
set -uo pipefail
BASE="${1:?informe a URL base, ex.: http://10.10.10.1:8080}"
OUT="${2:?informe a pasta de saida}"
CE_EXPECTED="${3:-404}"
mkdir -p "$OUT"
DIGEST=$(python3 "$(dirname "$0")/expected_digest.py" 20000)
REPORT="$OUT/functional-tests.txt"
ts() { python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).isoformat(timespec="milliseconds"))'; }
echo "Testes funcionais - $(ts) - base=$BASE - digest esperado (n=20000)=$DIGEST" > "$REPORT"
fails=0
check() {  # nome url status_esperado [trecho_esperado_no_corpo]
  local name="$1" url="$2" exp="$3" body_exp="${4:-}"
  local res code t
  res=$(curl -sS -o "$OUT/$name.body" -D "$OUT/$name.headers" -H "X-Run-ID: functional-$name" \
        -w '%{http_code} %{time_total}' "$url" 2>"$OUT/$name.err") || true
  code=${res%% *}; t=${res##* }
  local ok=1
  [[ "$code" == "$exp" ]] || ok=0
  if [[ -n "$body_exp" ]] && ! grep -q "$body_exp" "$OUT/$name.body" 2>/dev/null; then ok=0; fi
  if (( ok )); then r=PASSOU; else r=FALHOU; fails=$((fails+1)); fi
  printf '%-16s %-7s status=%s (esperado %s) tempo=%ss  %s\n' "$name" "$r" "$code" "$exp" "$t" "$url" | tee -a "$REPORT"
}
check health          "$BASE/health"                200 '"status":"ok"'
check work-n20000     "$BASE/work?n=20000"          200 "$DIGEST"
check work-n0         "$BASE/work?n=0"              422
check work-texto      "$BASE/work?n=abc"            422
check work-n100001    "$BASE/work?n=100001"         422
check controlled-err  "$BASE/controlled-error"      "$CE_EXPECTED"
echo "Resultado: $fails falha(s)" | tee -a "$REPORT"
exit "$fails"
