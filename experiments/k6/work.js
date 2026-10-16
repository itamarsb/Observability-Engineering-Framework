// k6 - carga de taxa constante sobre GET /work (uma requisicao por iteracao).
// Uso (WSL do notebook), com variaveis de ambiente:
//   BASE_URL=http://10.10.10.1:8080 N=20000 EXPECTED_DIGEST=<hex> RATE=16 \
//   DURATION=240s RUN_ID=C0-r01-... k6 run experiments/k6/work.js
//
// Metricas proprias:
//   failed      (Rate)  -> 1 quando status != 200 OU corpo incorreto (erro composto)
//   ok_duration (Trend) -> duracao (ms) SOMENTE das respostas corretas (SLI de latencia)
// Sem retries e sem redirects: uma iteracao = uma tentativa HTTP.
import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const failed = new Rate('failed');
const okDuration = new Trend('ok_duration', true);

const base = __ENV.BASE_URL;
const digest = __ENV.EXPECTED_DIGEST;
const n = Number(__ENV.N || 20000);
if (!base || !digest) {
  throw new Error('BASE_URL e EXPECTED_DIGEST sao obrigatorios');
}

export const options = {
  discardResponseBodies: false,
  scenarios: {
    work: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 5),
      timeUnit: '1s',
      duration: __ENV.DURATION || '240s',
      preAllocatedVUs: Number(__ENV.PRE_VUS || 50),
      maxVUs: Number(__ENV.MAX_VUS || 100),
      gracefulStop: '5s',
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(95)', 'p(99)', 'count'],
};

export default function () {
  const r = http.get(`${base}/work?n=${n}`, {
    timeout: __ENV.HTTP_TIMEOUT || '2s',
    redirects: 0,
    headers: { 'X-Run-ID': __ENV.RUN_ID || 'pilot', 'User-Agent': 'tcc2-k6' },
    tags: { name: 'GET /work' },
  });
  let valid = false;
  try {
    const b = r.json();
    valid = r.status === 200 && b.n === n && b.digest === digest;
  } catch (_) {
    valid = false;
  }
  check(r, { 'status e conteudo corretos': () => valid });
  failed.add(!valid);
  if (valid) {
    okDuration.add(r.timings.duration);
  }
}
