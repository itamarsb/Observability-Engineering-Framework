# Architecture and Workflows

**Language:** [Português (Brasil)](README.md) | **English (US)**

Framework diagrams written in [Mermaid](https://mermaid.js.org/) and rendered directly by GitHub. They describe the planned design and will be updated to reflect the actual deployed configuration after the integration stage (Stage 4B).

The overall diagram is available in the main [README](../../README.en.md#architecture).

| # | Diagram | What it shows |
|---|---|---|
| 1 | [Lab topology](#1-lab-topology) | Machines, networks, containers, and published ports |
| 2 | [Telemetry pipeline](#2-telemetry-pipeline) | How traces, metrics, and logs travel from the application to the backends |
| 3 | [Request flow](#3-request-flow) | A `GET /work` request and the telemetry it generates |
| 4 | [Run phases](#4-run-phases) | Time windows for load and perturbation scenarios |
| 5 | [Run orchestration](#5-run-orchestration) | What the orchestrator does, from initial checks to checksums |
| 6 | [Data and evidence flow](#6-data-and-evidence-flow) | From raw run data to tables, figures, and the paper |
| 7 | [Implementation and evaluation stages](#7-implementation-and-evaluation-stages) | Stages 0 through 11 and the protocol freeze |

---

## 1. Lab topology

```mermaid
flowchart LR
    subgraph NB["Laptop · Windows 11"]
        subgraph WSL["WSL2 · Ubuntu"]
            K6["k6"]
            PROBE["External probe"]
            ORCH["Orchestration<br/>and analysis"]
        end
        BROWSER["Browser<br/>localhost:3000"]
        TERM["Windows Terminal<br/>SSH and tunneling"]
    end

    ROUTER(["Wi-Fi router<br/>internet access and updates only"])

    subgraph SRV["Lab server · Ubuntu Server 26.04 LTS"]
        SSHD["sshd :22"]
        PERT["Perturbation scripts<br/>stress-ng units · tc netem"]
        NODE["node-exporter<br/>host network :9100"]
        subgraph DC["Docker Compose · lab network 172.30.0.0/24"]
            NGINX["nginx<br/>published at 10.10.10.1:8080"]
            API["api<br/>172.30.0.10:8000"]
            COL["collector"]
            BACK["prometheus · loki · tempo · grafana<br/>published only on 127.0.0.1"]
        end
    end

    K6 -->|"HTTP · Ethernet"| NGINX
    PROBE -->|"HTTP · Ethernet"| NGINX
    ORCH -->|"SSH · Ethernet"| SSHD
    BROWSER --> TERM
    TERM -->|"SSH · Ethernet"| SSHD
    SSHD -->|"restricted sudo"| PERT
    SSHD -->|"tunnel to 127.0.0.1"| BACK
    NGINX --> API --> COL --> BACK
    NODE -.->|scrape| BACK
    ROUTER -.-|Wi-Fi| TERM
    ROUTER -.-|Wi-Fi| SSHD
```

The laptop and server are connected by a dedicated Ethernet cable (`10.10.10.2` ↔ `10.10.10.1`, with no gateway), which carries the workload, probe traffic, and SSH traffic. Wi-Fi is used only for internet access and updates so that its latency variations do not affect measurements. NGINX is the only application port intentionally published on the dedicated network.

Node Exporter uses `network_mode: host`, and port 9100 requires verification of listening interfaces and firewall rules; administrative interfaces are accessible through the SSH tunnel.

---

## 2. Telemetry pipeline

```mermaid
flowchart LR
    subgraph APP["api container · OpenTelemetry SDK"]
        SDK_T["TracerProvider<br/>BatchSpanProcessor"]
        SDK_M["MeterProvider<br/>export every 5 s"]
        SDK_L["LoggerProvider<br/>BatchLogRecordProcessor"]
    end

    subgraph COLL["OpenTelemetry Collector"]
        RCV["otlp receiver<br/>HTTP :4318"]
        PROC["processors<br/>memory_limiter → batch"]
        EXP_T["exporter<br/>otlp_grpc/tempo"]
        EXP_M["prometheus exporter<br/>:8889"]
        EXP_L["exporter<br/>otlp_http/loki"]
        SELF["internal metrics<br/>:8888"]
    end

    NODE["Node Exporter<br/>:9100"]
    TEMPO[("Tempo<br/>traces · 90 days")]
    LOKI[("Loki<br/>logs · 90 days")]
    PROM[("Prometheus<br/>metrics · 90 days")]
    GRAF["Grafana"]

    SDK_T -->|OTLP/HTTP| RCV
    SDK_M -->|OTLP/HTTP| RCV
    SDK_L -->|OTLP/HTTP| RCV
    RCV --> PROC
    PROC -->|traces| EXP_T
    PROC -->|metrics| EXP_M
    PROC -->|logs| EXP_L
    EXP_T -->|"OTLP/gRPC :4317"| TEMPO
    EXP_L -->|"OTLP/HTTP /otlp"| LOKI
    EXP_M -.->|"scrape · 5 s"| PROM
    SELF -.->|"scrape · 5 s"| PROM
    NODE -.->|"scrape · 5 s"| PROM
    TEMPO -->|TraceQL| GRAF
    LOKI -->|LogQL| GRAF
    PROM -->|PromQL| GRAF
```

Traces and logs are **sent** by the Collector to Tempo and Loki; metrics are exposed by the Collector and **scraped** by Prometheus. In Grafana, the `trace_id` in each log opens the corresponding trace in Tempo, and each trace links back to its logs.

---

## 3. Request flow

```mermaid
sequenceDiagram
    autonumber
    participant K6 as k6 (laptop)
    participant NG as NGINX
    participant API as FastAPI application
    participant COL as OTel Collector
    participant BE as Tempo · Loki · Prometheus

    K6->>NG: GET /work?n=20000 with the X-Run-ID header
    NG->>API: forwarded over a keepalive connection
    activate API
    Note over API: start of the GET /work server span<br/>run_id recorded as a span attribute
    API->>API: child span validar_entrada
    API->>API: child span calcular_hash (SHA-256 applied n times)
    Note over API: request_completed log emitted within the span<br/>with trace_id and span_id
    API-->>NG: 200 with n and digest
    deactivate API
    NG-->>K6: 200 with n and digest
    Note over NG: JSON access log with request_time and run_id
    Note over K6: success only if the status is 200 and the digest is correct
    API-)COL: batched spans, duration histogram, and logs (OTLP/HTTP)
    COL-)BE: traces to Tempo, logs to Loki, metrics exposed for scraping
```

The same `trace_id` appears in the request trace (Tempo) and log (Loki), making correlation verifiable. The `run_id` links both to the run directory; it is never used as a metric label.

---

## 4. Run phases

```mermaid
flowchart TB
    subgraph LOAD["C0–C3 · load scenarios · 240 s"]
        direction LR
        W1["Warm-up<br/>60 s<br/>excluded"] --> M1["Measurement phase<br/>180 s"]
    end

    subgraph PERT["C4–C7 · perturbation scenarios · 600 s (C7: 480 s)"]
        direction LR
        W2["Warm-up<br/>60 s<br/>excluded"] --> B["Before<br/>180 s"] --> D["During<br/>180 s of perturbation<br/>C7: 60 s with the API stopped"] --> A["After<br/>180 s<br/>recovery"]
    end

    LOAD ~~~ PERT
```

Requests are assigned to phases according to their completion timestamps. In scenarios C4–C7, the start and end of the perturbation are recorded by the server itself and aligned with client data using the clock offset measured during the run. Recovery is reached at the first 30 s window with P95 ≤ 1.2 × the P95 of the *before* phase and no failures, sustained for 60 s.

---

## 5. Run orchestration

```mermaid
sequenceDiagram
    participant OP as Operator
    participant OR as Orchestrator (WSL)
    participant GEN as k6, probe, and monitoring tools
    participant SV as Lab server

    OP->>OR: run_scenario.sh C4 r02 campaign
    OR->>OR: checks for a clean Git working tree and records the commit
    OR->>SV: SSH: clock, server commit, services, and active stressors
    alt clock offset above 1 s, different commits, or an active stressor
        OR-->>OP: aborts before measurement
    end
    OR->>OR: writes manifest.json
    OR->>GEN: starts ping, the probe, and laptop metric sampling
    OR->>GEN: starts k6 (warm-up and phases)
    opt C4 through C7, at the start of the during phase
        OR->>SV: SSH sudo script tcc2-cpu / mem / net / apifail
        SV-->>OR: events-server.csv with start and end times from the server clock
    end
    GEN-->>OR: k6 finishes, 20 s drain period, probe and monitors stop
    OR->>SV: SSH export_run.py: Prometheus, Loki, Tempo, containers, journal
    SV-->>OR: exports copied to the run directory
    OR->>OR: final manifest, preliminary analysis, notes.md, checksums.sha256
    OP->>OR: reviews the run and records its validity in notes.md
```

Each run produces a self-contained directory, `runs/<pilot|campaign>/<scenario>-<repetition>-<UTC timestamp>/`. An interrupted run or one classified as invalid is retained and marked, never deleted.

---

## 6. Data and evidence flow

```mermaid
flowchart LR
    RUN[("Run directory<br/>manifest · raw k6 data · probe<br/>server exports · checksums")]
    BK[("Three copies<br/>WSL · Windows + external drive · cloud")]
    AN["analyze_run.py<br/>phases.csv · windows.csv · summary.json"]
    CHK{"Valid run?<br/>notes.md"}
    INV["Retained and marked INVALIDA<br/>scenario repeated"]
    CONS["consolidate.py<br/>summary-runs.csv<br/>summary-scenarios.csv"]
    FIG["plot_load.py · plot_run.py<br/>300 dpi PNG figures"]
    IDX["evidence-index.csv"]
    ART["Paper<br/>tables, figures, and appendices"]

    RUN --> AN --> CHK
    CHK -->|yes| CONS --> FIG --> ART
    CHK -->|no| INV
    RUN -.->|"same day"| BK
    CONS -.-> IDX
    FIG -.-> IDX
    IDX -.-> ART
```

Every number in the paper must be traceable to a file: the evidence index records the source file, the script or query that produced it, and where it is used.

---

## 7. Implementation and evaluation stages

```mermaid
flowchart LR
    subgraph PREP["Preparation"]
        direction TB
        S0["Stage 0<br/>access, inventory, and backup"] --> S1["Stage 1<br/>wired network, UTC clock, and Docker"] --> S2["Stage 2<br/>same commit on both machines"]
    end

    subgraph BUILD["Build and integration"]
        direction TB
        S3["Stage 3<br/>API behind NGINX and functional tests"] --> S4A["Stage 4A<br/>instrumentation verified with the debug exporter"] --> S4B["Stage 4B<br/>backends and log-to-trace correlation proof"] --> S5["Stage 5<br/>dashboards, queries, and exports"]
    end

    subgraph CAL["Calibration"]
        direction TB
        S6["Stage 6<br/>pilots: capacity ramp, workloads,<br/>targets, and perturbations"] --> S7{{"Stage 7<br/>protocol v1 frozen<br/>commit and tag"}}
    end

    subgraph MEAS["Measurement and analysis"]
        direction TB
        S8["Stage 8<br/>campaign: C0 and C2–C6 (+C7)<br/>3 blocks, 3 repetitions"] --> S9["Stage 9<br/>analysis: SLIs vs. SLOs"] --> S10["Stage 10<br/>evidence index and final figures"]
    end

    S2 --> S3
    S5 --> S6
    S7 --> S8
    S7 -.->|"change requested"| V2["Protocol v2<br/>reason documented"]
    V2 -.->|"repeat affected scenarios"| S8
```

A stage begins only after the previous one meets its exit criterion, as recorded in the lab logbook. Targets, workloads, and time windows are frozen before the campaign; any subsequent change results in a new protocol version rather than modifying the previous one.

---

[Return to the documentation index](../README.en.md)
