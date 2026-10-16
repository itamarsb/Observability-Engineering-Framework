# Architecture and workflows

Diagrams of the framework, written in [Mermaid](https://mermaid.js.org/) and rendered directly by GitHub. They describe the planned design and will be updated to the configuration actually deployed after the integration stage (Stage 4B).

The overview diagram is in the main [README](../../README.md#architecture).

| # | Diagram | What it shows |
|---|---|---|
| 1 | [Lab topology](#1-lab-topology) | Machines, networks, containers and published ports |
| 2 | [Telemetry pipeline](#2-telemetry-pipeline) | How traces, metrics and logs travel from the application to the back-ends |
| 3 | [Life of a request](#3-life-of-a-request) | One `GET /work` request and the telemetry it produces |
| 4 | [Phases of a run](#4-phases-of-a-run) | Time windows of load and perturbation scenarios |
| 5 | [Orchestration of a run](#5-orchestration-of-a-run) | What the orchestrator does from the pre-checks to the checksums |
| 6 | [Data and evidence flow](#6-data-and-evidence-flow) | From raw run data to tables, figures and the article |
| 7 | [Implementation and evaluation stages](#7-implementation-and-evaluation-stages) | Stages 0 to 11 and the protocol freeze |

---

## 1. Lab topology

```mermaid
flowchart LR
    subgraph NB["Notebook · Windows 11"]
        subgraph WSL["WSL2 · Ubuntu"]
            K6["k6"]
            PROBE["External probe"]
            ORCH["Orchestrator<br/>and analysis"]
        end
        BROWSER["Browser<br/>localhost:3000"]
        TERM["Windows Terminal<br/>SSH and tunnel"]
    end

    ROUTER(["Wi-Fi router<br/>internet and updates only"])

    subgraph SRV["Lab server · Ubuntu Server 26.04 LTS"]
        SSHD["sshd :22"]
        PERT["Perturbation scripts<br/>stress-ng units · tc netem"]
        NODE["node-exporter<br/>host network :9100"]
        subgraph DC["Docker Compose · network lab 172.30.0.0/24"]
            NGINX["nginx<br/>published on 10.10.10.1:8080"]
            API["api<br/>172.30.0.10:8000"]
            COL["collector"]
            BACK["prometheus · loki · tempo · grafana<br/>published on 127.0.0.1 only"]
        end
    end

    K6 -->|"HTTP · cable"| NGINX
    PROBE -->|"HTTP · cable"| NGINX
    ORCH -->|"SSH · cable"| SSHD
    BROWSER --> TERM
    TERM -->|"SSH · cable"| SSHD
    SSHD -->|"restricted sudo"| PERT
    SSHD -->|"tunnel to 127.0.0.1"| BACK
    NGINX --> API --> COL --> BACK
    NODE -.->|scraped| BACK
    ROUTER -.-|Wi-Fi| TERM
    ROUTER -.-|Wi-Fi| SSHD
```

The notebook and the server are linked by a dedicated Ethernet cable (`10.10.10.2` ↔ `10.10.10.1`, no gateway), which carries the workload, the probe and SSH. Wi-Fi is used only for internet access and updates, so its latency variation does not affect the measurements. Only NGINX is published on the lab network; the administrative interfaces are reachable only through the SSH tunnel.

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
        RCV["receiver otlp<br/>HTTP :4318"]
        PROC["processors<br/>memory_limiter → batch"]
        EXP_T["exporter<br/>otlp_grpc/tempo"]
        EXP_M["exporter prometheus<br/>:8889"]
        EXP_L["exporter<br/>otlp_http/loki"]
        SELF["internal metrics<br/>:8888"]
    end

    NODE["Node Exporter<br/>:9100"]
    TEMPO[("Tempo<br/>traces · 90 d")]
    LOKI[("Loki<br/>logs · 90 d")]
    PROM[("Prometheus<br/>metrics · 90 d")]
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
    EXP_M -.->|"scraped · 5 s"| PROM
    SELF -.->|"scraped · 5 s"| PROM
    NODE -.->|"scraped · 5 s"| PROM
    TEMPO -->|TraceQL| GRAF
    LOKI -->|LogQL| GRAF
    PROM -->|PromQL| GRAF
```

Traces and logs are **pushed** by the Collector to Tempo and Loki; metrics are exposed by the Collector and **pulled** by Prometheus. In Grafana, the `trace_id` carried by each log opens the matching trace in Tempo, and each trace links back to its logs.

---

## 3. Life of a request

```mermaid
sequenceDiagram
    autonumber
    participant K6 as k6 (notebook)
    participant NG as NGINX
    participant API as FastAPI application
    participant COL as OTel Collector
    participant BE as Tempo · Loki · Prometheus

    K6->>NG: GET /work?n=20000 with X-Run-ID header
    NG->>API: proxied over a keepalive connection
    activate API
    Note over API: server span GET /work starts<br/>run_id stored as a span attribute
    API->>API: child span validar_entrada
    API->>API: child span calcular_hash (SHA-256 applied n times)
    Note over API: request_completed log emitted inside the span<br/>with trace_id and span_id
    API-->>NG: 200 with n and digest
    deactivate API
    NG-->>K6: 200 with n and digest
    Note over NG: JSON access log with request_time and run_id
    Note over K6: success only if status is 200 and the digest is correct
    API-)COL: spans, duration histogram and logs in batches (OTLP/HTTP)
    COL-)BE: traces to Tempo, logs to Loki, metrics exposed for scraping
```

The same `trace_id` appears in the trace (Tempo) and in the log (Loki) of the request, which is what makes the correlation verifiable. The `run_id` links both to the run folder; it is never used as a metric label.

---

## 4. Phases of a run

```mermaid
flowchart TB
    subgraph LOAD["C0–C3 · load scenarios · 240 s"]
        direction LR
        W1["Warm-up<br/>60 s<br/>discarded"] --> M1["Main phase<br/>180 s"]
    end

    subgraph PERT["C4–C7 · perturbation scenarios · 600 s (C7: 480 s)"]
        direction LR
        W2["Warm-up<br/>60 s<br/>discarded"] --> B["Before<br/>180 s"] --> D["During<br/>180 s of perturbation<br/>C7: 60 s API stop"] --> A["After<br/>180 s<br/>recovery"]
    end

    LOAD ~~~ PERT
```

Requests are assigned to phases by completion time. For C4–C7, the perturbation start and end are recorded by the server and aligned with the client data using the clock offset measured in the run. Recovery is reached at the first 30 s window with P95 ≤ 1.2 × the *before* P95 and no failures, sustained for 60 s.

---

## 5. Orchestration of a run

```mermaid
sequenceDiagram
    participant OP as Operator
    participant OR as Orchestrator (WSL)
    participant GEN as k6, probe and meters
    participant SV as Lab server

    OP->>OR: run_scenario.sh C4 r02 campaign
    OR->>OR: check clean Git tree and record commit
    OR->>SV: SSH: clock offset, server commit, services, active stressors
    alt offset above 1 s, different commits or stressor active
        OR-->>OP: abort before measuring
    end
    OR->>OR: write manifest.json
    OR->>GEN: start ping, probe and notebook sampling
    OR->>GEN: start k6 for warm-up and phases
    opt C4 to C7, at the start of the during phase
        OR->>SV: SSH sudo tcc2-cpu / mem / net / apifail script
        SV-->>OR: events-server.csv with start and end in server time
    end
    GEN-->>OR: k6 ends, 20 s drain, probe and meters stopped
    OR->>SV: SSH export_run.py: Prometheus, Loki, Tempo, containers, journal
    SV-->>OR: exports copied into the run folder
    OR->>OR: final manifest, preliminary analysis, notes.md, checksums.sha256
    OP->>OR: review the run and record its validity in notes.md
```

Each run produces one self-contained folder, `runs/<pilot|campaign>/<scenario>-<repetition>-<UTC timestamp>/`. A run interrupted or classified as invalid is kept and marked, never deleted.

---

## 6. Data and evidence flow

```mermaid
flowchart LR
    RUN[("Run folder<br/>manifest · k6 raw · probe<br/>server exports · checksums")]
    BK[("Three copies<br/>WSL · Windows + external disk · cloud")]
    AN["analyze_run.py<br/>phases.csv · windows.csv · summary.json"]
    CHK{"Valid run?<br/>notes.md"}
    INV["Kept and marked INVALID<br/>scenario repeated"]
    CONS["consolidate.py<br/>summary-runs.csv<br/>summary-scenarios.csv"]
    FIG["plot_load.py · plot_run.py<br/>figures, PNG 300 dpi"]
    IDX["evidence-index.csv"]
    ART["Article<br/>tables, figures, appendices"]

    RUN --> AN --> CHK
    CHK -->|yes| CONS --> FIG --> ART
    CHK -->|no| INV
    RUN -.->|"same day"| BK
    CONS -.-> IDX
    FIG -.-> IDX
    IDX -.-> ART
```

Every number in the article must be traceable to a file: the evidence index records the source file, the script or query that produced it, and where it is used.

---

## 7. Implementation and evaluation stages

```mermaid
flowchart LR
    subgraph PREP["Preparation"]
        direction TB
        S0["Stage 0<br/>access, inventory, backup"] --> S1["Stage 1<br/>wired network, UTC clock, Docker"] --> S2["Stage 2<br/>same commit on both machines"]
    end

    subgraph BUILD["Build and integration"]
        direction TB
        S3["Stage 3<br/>API behind NGINX, functional tests"] --> S4A["Stage 4A<br/>instrumentation proven with debug exporter"] --> S4B["Stage 4B<br/>back-ends and log-to-trace proof"] --> S5["Stage 5<br/>dashboards, queries, export"]
    end

    subgraph CAL["Calibration"]
        direction TB
        S6["Stage 6<br/>pilots: capacity ramp, loads,<br/>targets, perturbations"] --> S7{{"Stage 7<br/>protocol v1 frozen<br/>commit and tag"}}
    end

    subgraph MEAS["Measurement and analysis"]
        direction TB
        S8["Stage 8<br/>campaign: C0–C6 (+C7)<br/>3 blocks, 3 repetitions"] --> S9["Stage 9<br/>analysis: SLIs vs SLOs"] --> S10["Stage 10<br/>redeployment from the repository"] --> S11["Stage 11<br/>evidence index, final figures"]
    end

    S2 --> S3
    S5 --> S6
    S7 --> S8
    S7 -.->|"change requested"| V2["Protocol v2<br/>reason recorded"]
    V2 -.->|"repeat affected scenarios"| S8
```

A stage starts only after the previous one meets its exit criterion, recorded in the lab log. Targets, loads and windows are frozen before the campaign; any later change creates a new protocol version instead of editing the previous one.
