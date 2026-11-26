# Experimental Matrix

**Language:** [Português (Brasil)](experimental-matrix.md) | **English (US)**

**Status:** draft. Workload levels, perturbation intensities, and targets are calibrated during the pilot runs and frozen in [`scenarios/protocol-v1.md`](scenarios/protocol-v1.md) before the experimental campaign. The approximate values below are starting points, not results.

## Common conditions

| Item | Definition |
|---|---|
| Operation | `GET /work?n=20000` through NGINX (port 8080) |
| Success | HTTP 200 **and** correct `n` and `digest` values in the response body |
| Load model | k6 `constant-arrival-rate`, one request per iteration, 2 s timeout, no retries or redirects |
| Load generator | Laptop (WSL2), external to the server, connected through the dedicated wired network |
| External probe | `GET /work` every 5 s, 2 s timeout, independent of k6 |
| Time windows | 60 s warm-up + 180 s measurement phase; C4–C6: 180 s each for the *before*, *during*, and *after* phases; C7: 180 s *before*, 60 s with the API stopped, and 180 s *after* |
| Phase assignment | Based on the request completion timestamp |
| Repetitions | 3 valid runs per scenario, in 3 blocks with varying run order |
| Interval between runs | At least 2 min, plus 60 s in a stable state |
| Clock | Server in UTC (chrony); clock offset between laptop and server measured in every run (limit: 1 s) |
| Identification | `run_id = <cenário>-<repetição>-<horário UTC>`, sent in the `X-Run-ID` header |

The `run_id` placeholders denote the scenario, repetition, and UTC timestamp, respectively.

## Scenarios

| ID | Scenario | Workload | Perturbation | Script / parameters |
|---|---|---|---|---|
| C0 | Baseline | R0 ≈ 20–25% of capacity | None | [`C0.env`](scenarios/C0.env) |
| C2 | Medium load | ≈ 40–50% of capacity | None | [`C2.env`](scenarios/C2.env) |
| C3 | High load | ≈ 70–80% of capacity | None | [`C3.env`](scenarios/C3.env) |
| C4 | CPU contention | R0 | `stress-ng --cpu 0 --cpu-load <piloto>` across the entire host | [`tcc2-cpu.sh`](stress-ng/tcc2-cpu.sh) |
| C5 | Memory pressure | R0 | `stress-ng --vm 1` under `MemoryMax`, with swap disabled for the unit | [`tcc2-mem.sh`](stress-ng/tcc2-mem.sh) |
| C6 | Network delay | R0 | `tc netem delay` on `eth0` in the NGINX container | [`tcc2-net.sh`](stress-ng/tcc2-net.sh) |
| C7 | Controlled API failure (optional) | R0 | API container stopped for 60 s and then restarted | [`tcc2-apifail.sh`](stress-ng/tcc2-apifail.sh) |

The `<piloto>` placeholder denotes the value determined during pilot calibration.

Capacity is measured beforehand using a stepped load ramp ([`k6/ramp.js`](k6/ramp.js), with 60 s steps). The *knee point* is the first step at which P95 latency doubles relative to the first step, failures occur, or `dropped_iterations > 0`.

The start and end of the perturbations are recorded by the server itself and aligned with client data using the measured clock offset.

## Block order

| Block | Order |
|---|---|
| 1 | C0, C2, C3, C4, C5, C6 |
| 2 | C2, C4, C6, C3, C0, C5 |
| 3 | C5, C3, C6, C0, C2, C4 |

C7, if retained, is run at the end of each block because it restarts the API.

## Per-run indicators

- P95 and P99 latency of correct responses (nearest-rank method).
- Composite error rate (status ≠ 200, incorrect response body, timeout, or connection error).
- Successful throughput and observed throughput.
- Sampled availability measured by the external probe (only when probe coverage is 100%).
- For C4–C7: change in P95 relative to the *before* phase and recovery time — the first 30 s window with P95 ≤ 1.2 × the P95 of the *before* phase and no failures, sustained for 60 s.
- Resource context: host CPU, available memory, network traffic, and temperature; items accepted, refused, and queued by the Collector.

## Safety limits

- Available memory maintained at a minimum of 2 GiB; free disk space at a minimum of 20 GiB.
- Maximum temperature defined after the pilot runs.
- A run that exceeds a limit is aborted, retained, and marked as invalid.

---

[Return to the documentation index](../docs/README.en.md)
