// k6 - rampa de capacidade (PILOTO): degraus de 60 s ate encontrar o "joelho".
// Joelho = primeiro degrau em que o P95 dobra em relacao ao primeiro degrau,
// surgem falhas ou dropped_iterations > 0. Os degraus podem ser ajustados por STEPS.
// Uso: BASE_URL=... EXPECTED_DIGEST=... RUN_ID=PILOT-ramp-... k6 run experiments/k6/ramp.js
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

// Degraus em RPS (cada um mantido por STEP_S segundos, com 10 s de transicao).
const steps = (__ENV.STEPS || '10,20,40,60,80,100,120').split(',').map(Number);
const stepS = Number(__ENV.STEP_S || 60);
const stages = [];
for (const rps of steps) {
  stages.push({ target: rps, duration: '10s' });
  stages.push({ target: rps, duration: `${stepS}s` });
}

export const options = {
  scenarios: {
    ramp: {
      executor: 'ramping-arrival-rate',
      startRate: steps[0],
      timeUnit: '1s',
      preAllocatedVUs: Number(__ENV.PRE_VUS || 100),
      maxVUs: Number(__ENV.MAX_VUS || 300),
      stages,
      gracefulStop: '5s',
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(95)', 'p(99)', 'count'],
};

export default function () {
  const r = http.get(`${base}/work?n=${n}`, {
    timeout: __ENV.HTTP_TIMEOUT || '2s',
    redirects: 0,
    headers: { 'X-Run-ID': __ENV.RUN_ID || 'pilot-ramp', 'User-Agent': 'tcc2-k6' },
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
