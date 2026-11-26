# Repository Audit and Pilot Preparation — October 20, 2026

**Language:** [Português (Brasil)](auditoria-repositorio-2026-10-20.md) | **English (US)**

> **Historical record:** This document describes the October 20, 2026 audit, its findings, and the validation status at that time. It is not a new audit or a statement about the current status of the pull request or the experimental environment.

**Scope and reference.** The initial audit examined the `Observability-Engineering-Framework-main(2).zip` copy and compared it with the v4 laboratory kit and the v3.1 Lab Bench Manual (Manual de Bancada v3.1). The modified files were then checked against the `main` branch and published for review in [Pull Request #1](https://github.com/itamarsb/Observability-Engineering-Framework/pull/1), on the `fix/tcc2-pre-piloto` branch. The checks were static and used synthetic data; no integration test was performed on the Mini PC.

## Technical changes incorporated

| Priority | Location | Issue in the original copy | Resolution in the revised package |
|---|---|---|---|
| High | `scripts/analyze_run.py` | Parser dependent on the textual formatting of k6 JSON output | Imported the v4 kit fix: parse the JSON and then check the record type |
| High | `scripts/run_scenario.sh` | The Git check ignored untracked files, and some failures were not explicitly marked | Imported the v4 fix and added the initial status `Classificacao final: PENDENTE` |
| High | `scripts/export_run.py` | Loki logs did not preserve structured metadata; export errors did not affect the exit status | Imported the v4 fix and added a check for selected Tempo traces that were not saved |
| High | `scripts/consolidate.py` | Any run with `analysis/phases.csv` could enter the summary if the text `INVALIDA` was absent, even if its validity was pending | Only `Classificacao final: VALIDA` permits consolidation; rejects duplicate runs with the same scenario/repetition combination |
| High | `scripts/backup_volumes.sh` | A backup failure could leave the stack stopped, and the target project was implicit | Imported the v4 fix, explicit selection with `-p "$PROJECT"`, an absolute path, and SHA-256 verification |
| Medium | `compose.yaml`, `.env.example` | Fixed Docker network/API IP settings made isolated redeployment difficult | Variables `LAB_DOCKER_SUBNET` and `API_IPV4`, retaining the existing defaults |
| Medium | `docs/runbooks/deployment.md` | Redeployment with a second network could conflict with the original network | Instructions for an isolated subnet. Manual `tc netem` recovery was retained |
| Medium | `README.md`, `docs/architecture/README.md` | The statement that only NGINX was exposed omitted Node Exporter with `network_mode: host` | Documented the exception and the need to check port 9100 |
| Medium | `results/README.md` | Human approval of runs before generating summaries was not explained | Added explicit approval and duplicate detection controls |
| Low | `.gitignore` | Additional safeguards for local artifacts were not documented | Added preventive exclusion rules without removing evidence or code already tracked by Git |
| Medium | `tests/test_pipeline_offline.py` | No automated regression tests existed for the analysis pipeline | Created synthetic unit tests using standard Python, without hardware or additional installations |

The contents of `app/`, the scenario matrix, dashboards, installation screenshots, and academic references were preserved except where indicated. The fixes were applied to the existing repository without replacing its documentation or visual evidence with files from the standalone kit.

## Caution: Validation still pending on the Mini PC

1. Validate the actual versions, `docker compose config -q`, container health, and Python and k6 dependencies.
2. Inspect `ss -ltnp | grep ':9100'` and firewall rules. Node Exporter using host networking may make the port accessible through other interfaces. Do not claim isolation without evidence.
3. Verify the API → OpenTelemetry Collector → Prometheus/Loki/Tempo sequence and the Grafana dashboard UIDs.
4. Verify the actual `job`, `http_route`, and `le` labels and the semantics of the PromQL queries in the API and dashboard 01.
5. Confirm that the same `trace_id` appears in Loki, Tempo, and the run export.
6. Deliberately simulate an incomplete export and verify that the run is classified as invalid.
7. Test backup, hash verification, and test restoration without overwriting campaign data.
8. Run C4–C7 only during supervised pilots, verifying that the stressors are cleaned up (`systemctl`, `tc`).
9. Visually inspect images and public screenshots before publishing new posts to avoid disclosing secrets, usernames, globally routable network addresses, tokens, or personal data.
10. Freeze validity criteria, workloads, and SLOs in the protocol before Stage 8, and record the commit/tag for the script and configuration versions.

**Verification limitations.** Syntax checks and tests with synthetic inputs do not establish operational compatibility of the pinned versions, effective retention, CPU/memory consumption, inter-container communication, k6 timeouts, or Mini PC performance. `run_scenario.sh` contains exception paths and privileged actions that require supervised pilots. This audit does not certify any campaign scenario.

## How to test the changes safely

In the local repository clone, run the read-only/validation commands without starting the stack:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
find scripts -name '*.py' -print0 | xargs -0 -r -n1 python3 -m py_compile
bash -n scripts/run_scenario.sh scripts/backup_volumes.sh
```

Human approval of a run (only after checking `notes.md`, raw data, and the exporter report):

```text
- Classificacao final: VALIDA
```

If in doubt, keep `PENDENTE`; for an invalid run, use `INVALIDA` and describe the reason. **Do not change validity criteria during the campaign.** The consolidation script does not independently determine whether the workload and resources were valid.

The literal classification field and status values remain in Portuguese for compatibility with the automation scripts.

## Version control and publication

The initial changes were published on October 20, 2026 (20/10/2026) in [Pull Request #1](https://github.com/itamarsb/Observability-Engineering-Framework/pull/1), opened as a draft against `main`. The initial review commit is `ecb8d3a`, and the subsequent PR history records additional editorial and technical adjustments.

- Compare the contents in the PR's **Files changed** tab before merging.
- Keep the PR in draft status until the checks in the preceding section have been completed in the lab.
- Avoid committing `.env`, credentials, `runs/`, and raw results that contain sensitive information.
- For subsequent changes, check the protocol revision and evidence record before updating the files.

---

[Return to the documentation index](../README.en.md)
