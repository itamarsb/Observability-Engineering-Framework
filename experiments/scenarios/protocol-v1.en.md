# Experimental Protocol — Version v1 (FROZEN on ____/____/2026, commit ________)

**Language:** [Português (Brasil)](protocol-v1.md) | **English (US)**

> **Status and source of truth:** This is a reference translation of the [authoritative Portuguese protocol](protocol-v1.md). The current configuration identifies the protocol as a draft (`PROTOCOL_VERSION=v1-rascunho`); the freeze date and commit above are unfilled placeholders, not evidence of a completed freeze. Calibration and SLO scripts read and update the original Portuguese file, not this translation. Synchronize this translation with the authoritative protocol after calibration and before publishing the frozen protocol; do not use this file as an automation input. If the two versions differ, the authoritative protocol takes precedence.

Complete ALL fields before the first definitive run. If anything changes, create protocol-v2.md,
document the reason, and repeat the affected scenarios. Do not change targets after reviewing the results.

| Field | Recorded decision |
|---|---|
| Application | commit ____; image tcc2-api:____ (ID ____); n = 20000; expected digest ____; 1 Uvicorn worker |
| Telemetry | Collector 0.162.0; Prometheus v3.15.0; Loki 3.7.8; Tempo 3.1.0; Grafana 13.1.3; digests in versions.txt; 100% sampling; 5 s scrape interval; 5 s metric export interval; buckets ____; 90 d retention |
| Load generator | laptop ____; WSL ____ (NAT/mirrored networking mode); k6 v____; constant-arrival-rate; 2 s timeout; no retries |
| Capacity (ramp) | knee point at ____ RPS (P95 ____ ms on the 1st step) |
| Workload levels | C0 = R0 = ____ RPS; C2 = ____ RPS; C3 = ____ RPS; C4-C7 = R0 (C1 removed from scope) |
| Time windows | 60 s warm-up; 180 s phase; C4-C6: 180 s each for before/during/after; phase assignment by completion timestamp |
| Perturbations | C4: stress-ng --cpu 0 --cpu-load ____; C5: --vm 1 --vm-bytes ____ MemoryMax ____; C6: netem delay ____ ms on NGINX eth0; C7 (optional): API stopped for 60 s |
| Probe | /work every 5 s; 2 s timeout; success = 200 + digest; minimum coverage 100% |
| Analysis | nearest-rank method; latency SLI population = correct responses; composite error rate; Delta P95; recovery (30 s / 1.2x / 60 s) |
| Validity | criteria applied by scripts/revisar_execucoes.py using the limits in validade.env. Load: k6 exit code 0, dropped_iterations = 0, and load generator CPU <= 85%; probe: 100% coverage; telemetry: export without errors, CPU and memory time series containing samples, no containers restarted or marked OOMKilled; intervention (C4-C7): start and end recorded by the server and exit code 0; integrity: checksums.sha256 verified. Technical failure = INVALIDA (invalid); dropped > 0 or load generator CPU above the limit = inconclusive (operator decision recorded in notes.md) |
| Targets (SLO) | P95 <= ____ ms; P99 <= ____ ms (rule: 2x C0 pilot, multiple of 25 ms); error rate <= 1%; availability >= 99%; successful throughput >= 95% of offered throughput; applied to the measurement phase (C0, C2, C3) and the during phase (C4-C7) |
| Order | block 1: C0 C2 C3 C4 C5 C6; block 2: C2 C4 C6 C3 C0 C5; block 3: C5 C3 C6 C0 C2 C4; interval >= 2 min + 60 s stable (campaign.env) |
| Safety | MemAvailable >= 2 GiB; free disk space >= 20 GiB; temperature < ____ C; abort and record |

---

[Return to the documentation index](../../docs/README.en.md) · [Experimental matrix](../experimental-matrix.en.md)
