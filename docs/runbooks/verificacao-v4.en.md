# Pre-Pilot Verification — Revision v4

**Language:** [Português (Brasil)](verificacao-v4.md) | **English (US)**

This checklist brings together the fixes submitted in [Pull Request #1](https://github.com/itamarsb/Observability-Engineering-Framework/pull/1) and the checks required before the definitive experimental campaign. Syntax checks and tests with synthetic data were performed while preparing the revision. **Integration on the Mini PC had not yet been tested at the time of the revision.**

## Changes to verify

- `run_scenario.sh`: check Git status on both machines and mark runs with k6, intervention, export, copy, or analysis failures as invalid.
- `export_run.py`: verify the export of Loki's `structured_metadata`, the handling of error responses, and the reporting of incomplete pagination.
- `analyze_run.py`: confirm the parsing of k6 JSON records and consistency with consolidation.
- `consolidate.py`: accept only runs approved in `notes.md` and block duplicate repetitions.
- `backup_volumes.sh`: verify the expected volumes, SHA-256 checksums, and restoration of services after an interruption.
- `compose.yaml` and `.env.example`: validate the parameterization of the network and the API's internal IP address, including in the redeployment environment.

## Mandatory checks before Stage 8

1. Record image versions, tags, and digests; run `docker compose config` on the Mini PC.
2. Inspect Node Exporter port 9100 and firewall rules. Restrict access before using third-party networks, without interrupting Prometheus data collection.
3. Confirm Stages 4A and 4B with metrics, logs, and traces from the same request, including correlation metadata.
4. Test the dashboard 01 queries using the labels actually exported (`job`, `http_route`, and `le`).
5. Run k6, the probe, and perturbations only during supervised pilot runs, verifying that the stressors are removed.
6. Verify the backup, hashes, and restoration to a test volume without modifying campaign data.
7. ~~Test redeployment on a separate subnet~~ (removed from scope: independent reproduction is left to third parties, based on the documentation).
8. Record workloads, validity and recovery criteria, and protocol targets before the definitive experimental campaign.

## Analysis criteria

Latency is measured for correct responses; errors are counted separately. Each scenario requires three valid repetitions, and pilot runs are excluded from the definitive results. The automated routine identifies some technical failures; the assessment of `dropped_iterations`, the effective load rate, probe coverage, and consistency of the applied stress must be recorded in `notes.md`.

If evidence is insufficient, keep the `PENDENTE` classification. Record the reason for `INVALIDA` before repeating a run. No scenario is qualified for the campaign solely by passing the offline tests.

**Automation compatibility:** `PENDENTE` (pending) and `INVALIDA` (invalid) are literal classification values and must remain unchanged in files consumed by the scripts.

---

[Return to the documentation index](../README.en.md)
