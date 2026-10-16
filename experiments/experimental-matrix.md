# Experimental matrix

**Status:** draft. Demands, intensities and targets are calibrated in pilot runs and frozen in [`scenarios/protocol-v1.md`](scenarios/protocol-v1.md) before the campaign. Values marked as approximate below are starting points, not results.

## Common conditions

| Item | Definition |
|---|---|
| Operation | `GET /work?n=20000` through NGINX (port 8080) |
| Success | HTTP 200 **and** correct `n` and `digest` in the body |
| Workload model | k6 `constant-arrival-rate`, one request per iteration, 2 s timeout, no retries, no redirects |
| Load generator | Notebook (WSL2), outside the server, over the dedicated wired network |
| External probe | `GET /work` every 5 s, 2 s timeout, independent of k6 |
| Windows | 60 s warm-up + 180 s phase; C4–C6: 180 s *before*, *during* and *after*; C7: 180 s *before*, 60 s API stop, 180 s *after* |
| Phase assignment | By request completion time |
| Repetitions | 3 valid runs per scenario, in 3 blocks with alternating order |
| Interval between runs | At least 2 min, plus 60 s of stable state |
| Clock | Server in UTC (chrony); notebook–server offset measured in every run (limit: 1 s) |
| Run identification | `run_id = <scenario>-<repetition>-<UTC timestamp>`, sent as the `X-Run-ID` header |

## Scenarios

| ID | Scenario | Demand | Perturbation | Script / parameters |
|---|---|---|---|---|
| C0 | Reference (baseline) | R0 ≈ 20–25% of capacity | None | [`C0.env`](scenarios/C0.env) |
| C1 | Low load | ≈ 5–10% of capacity | None | [`C1.env`](scenarios/C1.env) |
| C2 | Medium load | ≈ 40–50% of capacity | None | [`C2.env`](scenarios/C2.env) |
| C3 | High load | ≈ 70–80% of capacity | None | [`C3.env`](scenarios/C3.env) |
| C4 | CPU contention | R0 | `stress-ng --cpu 0 --cpu-load <pilot>` on the whole host | [`tcc2-cpu.sh`](stress-ng/tcc2-cpu.sh) |
| C5 | Memory pressure | R0 | `stress-ng --vm 1` under `MemoryMax`, no swap for the unit | [`tcc2-mem.sh`](stress-ng/tcc2-mem.sh) |
| C6 | Network delay | R0 | `tc netem delay` on `eth0` of the NGINX container | [`tcc2-net.sh`](stress-ng/tcc2-net.sh) |
| C7 | Controlled API failure (optional) | R0 | API container stopped for 60 s, then restarted | [`tcc2-apifail.sh`](stress-ng/tcc2-apifail.sh) |

Capacity is measured beforehand with a stepped ramp ([`k6/ramp.js`](k6/ramp.js), 60 s steps). The *knee* is the first step in which the P95 latency doubles relative to the first step, failures appear, or `dropped_iterations > 0`.

Perturbation start and end times are recorded by the server itself and aligned with the client data using the measured clock offset.

## Block order

| Block | Order |
|---|---|
| 1 | C0, C1, C2, C3, C4, C5, C6 |
| 2 | C2, C4, C6, C1, C3, C0, C5 |
| 3 | C5, C3, C1, C6, C0, C2, C4 |

C7, if kept, is run at the end of each block, because it restarts the API.

## Indicators per run

- P95 and P99 latency of correct responses (nearest-rank method).
- Composite error rate (status ≠ 200, incorrect body, timeout or connection error).
- Successful and observed throughput.
- Sampled availability from the external probe (only when probe coverage is 100%).
- For C4–C7: change in P95 relative to the *before* phase, and recovery time — first 30 s window with P95 ≤ 1.2 × the *before* P95 and no failures, sustained for 60 s.
- Resource context: host CPU, available memory, network traffic and temperature; Collector accepted, refused and queued items.

## Safety limits

- Available memory kept at or above 2 GiB; free disk at or above 20 GiB.
- Maximum temperature defined after the pilot runs.
- A run that crosses a limit is aborted, kept and marked as invalid.
