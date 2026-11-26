# Files Reviewed for the Pre-Pilot Stage — v4

**Language:** [Português (Brasil)](arquivos-alterados-v4.md) | **English (US)**

> **Historical record:** This document describes the scope and validation status at the time of the original review, not the current state of the repository.

This record identifies the files proposed in [Pull Request #1](https://github.com/itamarsb/Observability-Engineering-Framework/pull/1) relative to the `main` branch when the review was opened: **12 modified and 4 added**. The PR history contains the details for each commit. Integration tests on the Mini PC remained pending at the time of this review.

## Application and data collection

| Path | Change |
|---|---|
| `scripts/analyze_run.py` | Reading JSON records exported by k6 |
| `scripts/run_scenario.sh` | Checking Git status and classifying technical failures |
| `scripts/export_run.py` | Exporting logs and traces, including Loki metadata and error handling |
| `scripts/consolidate.py` | Including only approved runs and detecting duplicate repetitions |
| `scripts/backup_volumes.sh` | Handling interruptions, bringing services back online, and ensuring file integrity |
| `tests/test_pipeline_offline.py` | Tests using synthetic data for analysis and consolidation **(new)** |

## Infrastructure and documentation

| Path | Change |
|---|---|
| `.env.example` | Docker network parameters for isolated deployment |
| `compose.yaml` | Network and API IP address configuration through variables |
| `.gitignore` | Exclusions for temporary artifacts and sensitive files |
| `README.md` | Updates to infrastructure status and limitations |
| `docs/architecture/README.md` | Revision of the description of service exposure |
| `docs/runbooks/deployment.md` | Isolated redeployment procedure |
| `results/README.md` | Run approval before consolidation |
| `docs/runbooks/verificacao-v4.md` | Pre-pilot verification checklist **(new)** |
| `docs/runbooks/auditoria-repositorio-2026-10-20.md` | Technical audit and validation limits **(new)** |
| `docs/runbooks/arquivos-alterados-v4.md` | This inventory of changes **(new)** |

The changes were checked through code and document review, syntax validation, and offline tests. Approval of the experimental protocol depends on the actual tests specified in the runbooks.

---

[Return to the documentation index](../README.en.md)
