<div align="center">

<p align="center">
    <img src="docs/images/Framework_Observability_Overview_18_59_51.png">
</p>
</div>


# Observability-Engineering-Framework

Final Project for the Undergraduate Degree in Computer Engineering, developing an Observability Engineering Framework using only open-source software and low-cost hardware.


# Open Source Observability Framework Lab

A practical observability framework built with OpenTelemetry,
Prometheus, Grafana, Loki and Tempo.

This project was developed as part of a Computer Engineering
research project focused on reliability engineering,
telemetry and distributed systems observability.


## Why?

Modern distributed systems generate huge amounts of telemetry.

This project demonstrates how an engineer can build a complete
observability stack using only open source technologies and
commodity hardware.


## Stack

- Python
- FastAPI
- OpenTelemetry
- Prometheus
- Grafana
- Loki
- Tempo
- Linux Ubuntu Server LTS
- NGINX
- K6
- Stress-NG


## General and Specific Objectives:

- Configure an experimental environment based on a Mini PC (focus on low-cost hardware) and the Linux Ubuntu Server LTS operating system;
- Develop and instrument a back-end application using FastAPI and OpenTelemetry;
- Integrate Prometheus, Grafana, Loki and Tempo for collecting, processing and analyzing telemetry signals;
- Execute load tests using K6 and chaos experiments with Stress-NG;
- Evaluate the system's behavior based on previously defined SLI indicators and SLO targets.


# Telemetry

Telemetry is the process of collecting and transmitting operational data from systems for monitoring, analysis and decision making.

Examples:

- Metrics
- Logs
- Traces

```mermaid

flowchart TB
    subgraph GEN["1. Traffic and Workload Generation"]
        USER["User"]
        K6["k6<br/>Load Testing"]
        STRESS["stress-ng<br/>Resource Stress"]
    end

    subgraph APP["2. Application Layer"]
        NGINX["NGINX<br/>Reverse Proxy"]
        FASTAPI["FastAPI<br/>Instrumented Application"]
        OTELSDK["OpenTelemetry SDK<br/>Telemetry Generation"]
    end

    subgraph COL["3. Collection and Processing"]
        OTELCOL["OpenTelemetry Collector<br/>Receive, Process and Export"]
        PROM["Prometheus<br/>Metrics Collection"]
    end

    subgraph STORE["4. Telemetry Storage"]
        LOKI["Loki<br/>Logs"]
        TEMPO["Tempo<br/>Traces"]
    end

    subgraph VIEW["5. Visualization and Analysis"]
        GRAFANA["Grafana<br/>Dashboards and Analysis"]
    end

    USER -->|HTTP requests| NGINX
    K6 -->|Load-test requests| NGINX
    NGINX --> FASTAPI

    STRESS -.->|CPU and memory pressure| FASTAPI

    FASTAPI -->|Instrumentation| OTELSDK
    OTELSDK -->|Logs and traces via OTLP| OTELCOL

    PROM -->|Scrapes /metrics| FASTAPI
    PROM -->|Scrapes internal metrics| OTELCOL

    OTELCOL -->|Exports logs| LOKI
    OTELCOL -->|Exports traces| TEMPO

    PROM -->|Metrics queries| GRAFANA
    LOKI -->|Log queries| GRAFANA
    TEMPO -->|Trace queries| GRAFANA

```

---

## Metrics

Metrics are numerical measurements collected over time.

Examples:

- CPU Usage
- Memory Usage
- Request Rate
- Error Rate


```mermaid

flowchart TB
    subgraph WORKLOAD["1. Workload Generation"]
        K6["k6<br/>Load Testing"]
        STRESS["stress-ng<br/>CPU and Memory Pressure"]
    end

    subgraph APPLICATION["2. Application Layer"]
        NGINX["NGINX<br/>Reverse Proxy"]
        FASTAPI["FastAPI<br/>Instrumented Application"]

        APPMETRICS["Application Metrics<br/>Request Rate • Error Rate<br/>P95 / P99 Latency<br/>Process CPU • Process Memory"]
    end

    subgraph COLLECTION["3. Metrics Collection and Storage"]
        OTELCOL["OpenTelemetry Collector<br/>Internal Metrics"]
        PROM["Prometheus<br/>Scraping and Time-Series Storage"]
    end

    subgraph ANALYSIS["4. Visualization and Evaluation"]
        GRAFANA["Grafana<br/>Dashboards and PromQL"]
        SLO["SLI / SLO Evaluation<br/>Availability • Latency<br/>Error Rate • Throughput"]
    end

    K6 -->|HTTP load| NGINX
    NGINX -->|Proxies requests| FASTAPI
    STRESS -.->|Resource pressure| FASTAPI

    FASTAPI --- APPMETRICS

    FASTAPI -->|Exposes /metrics<br/>scraped by Prometheus| PROM
    OTELCOL -->|Exposes internal metrics<br/>scraped by Prometheus| PROM

    PROM -->|PromQL queries| GRAFANA
    GRAFANA -->|Dashboard analysis| SLO

```

---

## Logs

Logs record events occurring in systems and applications.

Use Cases:

- Troubleshooting
- Auditing
- Root Cause Analysis


```mermaid

flowchart TB
    subgraph TRAFFIC["1. Traffic Generation"]
        USER["User"]
        K6["k6<br/>Load Testing"]
    end

    subgraph SOURCES["2. Log Sources"]
        NGINX["NGINX<br/>Reverse Proxy"]
        FASTAPI["FastAPI<br/>Instrumented Application"]

        NLOGS["NGINX Logs<br/>Access • Error"]
        ALOGS["Application Logs<br/>Request • Error • Business Events"]
    end

    subgraph COLLECTION["3. Collection and Processing"]
        OTELSDK["OpenTelemetry SDK<br/>Structured Log Generation"]
        OTELCOL["OpenTelemetry Collector<br/>Receive • Enrich • Batch • Export"]
    end

    subgraph STORAGE["4. Log Storage"]
        LOKI["Loki<br/>Log Aggregation and Storage"]
    end

    subgraph ANALYSIS["5. Visualization and Analysis"]
        GRAFANA["Grafana<br/>LogQL Queries and Dashboards"]
        OUTCOMES["Troubleshooting<br/>Error Investigation<br/>Root Cause Analysis"]
    end

    USER -->|HTTP requests| NGINX
    K6 -->|Load-test requests| NGINX
    NGINX -->|Proxies requests| FASTAPI

    NGINX -->|Generates| NLOGS
    FASTAPI -->|Generates| ALOGS

    NLOGS -.->|Filelog receiver| OTELCOL
    ALOGS -->|Structured logs| OTELSDK
    OTELSDK -->|OTLP| OTELCOL

    OTELCOL -->|Exports logs via OTLP/HTTP| LOKI
    LOKI -->|LogQL queries| GRAFANA
    GRAFANA -->|Supports| OUTCOMES

```
---

## Traces

Traces follow a request through distributed systems.

Components:

- Trace
- Span

Benefits:

- Performance Analysis
- Dependency Mapping
- Root Cause Investigation

```mermaid
flowchart TD

    USER[User or K6 Load Test]
    NGINX[NGINX<br/>Reverse Proxy]
    FASTAPI[FastAPI<br/>Instrumented Application]
    OTELSDK[OpenTelemetry SDK<br/>Trace Generation]
    OTELCOL[OpenTelemetry Collector<br/>Processing and Export]
    TEMPO[Grafana Tempo<br/>Trace Storage]
    GRAFANA[Grafana<br/>Trace Visualization]

    USER --> NGINX
    NGINX --> FASTAPI
    FASTAPI --> OTELSDK
    OTELSDK --> OTELCOL
    OTELCOL --> TEMPO
    TEMPO --> GRAFANA
```


---


## Service Objectives

- Latency P95 < 200ms;
- Error Rate < 1%;
- Availability > 99%;
- CPU Usage < 80%.


## Experimental Environment:

- Hardware: Intel Core i7 Mini PC, operating as a local server (NGINX);
- Operating System: Compatible Linux distribution (Ubuntu Server LTS);
- Back-end Application: API developed in Python using FastAPI;
- Telemetry Layer: Instrumentation with OpenTelemetry SDK;
- Observability Services:
  - Prometheus (metrics collection);
  - Grafana (visualization);
  - Loki (log storage);
  - Tempo (distributed traces);
  - OpenTelemetry Collector (routing and standardization of telemetry).
- Testing Tools:
  - K6 (load testing);
  - Stress-NG (chaos engineering with overload testing).

---
## Roadmap:

- PHYSICAL ENVIRONMENT PREPARATION:

- [X] Installation of the Linux operating system on the Mini PC;

![Preparation](/docs/images/Ubuntu_Server_18.jpg)

- [X] Network configuration, permissions and working directories.

![Preparation](/docs/images/Ubuntu_Server_20.jpg)


- OBSERVABILITY ECOSYSTEM CONFIGURATION:

- [ ] Deployment of Prometheus, Grafana, Loki and Tempo;

- [ ] Configuration of basic dashboards in Grafana;

- [ ] Creation of scraping jobs in Prometheus.


- TEST APPLICATION DEVELOPMENT:

- [ ] Implementation of a back-end service with FastAPI;

- [ ] Definition of routes, handlers and representative operations;

- [ ] Packaging and execution of the application.


- INSTRUMENTATION WITH OPENTELEMETRY:

- [ ] Addition of tracing middleware, metrics and logs;

- [ ] Export to OpenTelemetry Collector;

- [ ] Standardization of the OTLP format.


- LOAD TESTING AND METRICS COLLECTION:

- [ ] Execution of test scenarios on K6 (low, medium and high load);

- [ ] Recording of latency, throughput, errors and saturation.


- CHAOS ENGINEERING EXPERIMENTS:

- [ ] Application of CPU, memory and network stressors with Stress-NG;

- [ ] Observation of the impact on SLIs.


- RESULTS ANALYSIS:

- [ ] Integrated visualization of telemetry in Grafana;

- [ ] Comparison with defined SLO targets;

- [ ] Interpretation of system behavior.

---

## 📈 Repository Metrics

<p align="center">
    
<a href="https://info.flagcounter.com/A1ey"><img src="https://s01.flagcounter.com/count/A1ey/bg_FFFFFF/txt_000000/border_CCCCCC/columns_8/maxflags_100/viewers_0/labels_1/pageviews_1/flags_0/percent_0/" alt="Flag Counter" border="0"></a>

</p>
