# Arquitetura e fluxos de trabalho

Diagramas do framework, escritos em [Mermaid](https://mermaid.js.org/) e renderizados diretamente pelo GitHub. Eles descrevem o desenho planejado e serão atualizados para a configuração efetivamente implantada após a etapa de integração (Etapa 4B).

O diagrama geral está no [README](../../README.md#arquitetura) principal.

| # | Diagrama | O que mostra |
|---|---|---|
| 1 | [Topologia do laboratório](#1-topologia-do-laboratório) | Máquinas, redes, contêineres e portas publicadas |
| 2 | [Pipeline de telemetria](#2-pipeline-de-telemetria) | Como traces, métricas e logs vão da aplicação até os back-ends |
| 3 | [Percurso de uma requisição](#3-percurso-de-uma-requisição) | Uma requisição `GET /work` e a telemetria que ela produz |
| 4 | [Fases de uma execução](#4-fases-de-uma-execução) | Janelas de tempo dos cenários de carga e de perturbação |
| 5 | [Orquestração de uma execução](#5-orquestração-de-uma-execução) | O que o orquestrador faz, das verificações iniciais às somas de verificação |
| 6 | [Fluxo de dados e evidências](#6-fluxo-de-dados-e-evidências) | Dos dados brutos de cada execução às tabelas, figuras e ao artigo |
| 7 | [Etapas de implementação e avaliação](#7-etapas-de-implementação-e-avaliação) | Etapas 0 a 11 e o congelamento do protocolo |

---

## 1. Topologia do laboratório

```mermaid
flowchart LR
    subgraph NB["Notebook · Windows 11"]
        subgraph WSL["WSL2 · Ubuntu"]
            K6["k6"]
            PROBE["Sonda externa"]
            ORCH["Orquestrador<br/>e análise"]
        end
        BROWSER["Navegador<br/>localhost:3000"]
        TERM["Windows Terminal<br/>SSH e túnel"]
    end

    ROUTER(["Roteador Wi-Fi<br/>somente internet e atualizações"])

    subgraph SRV["Servidor do laboratório · Ubuntu Server 26.04 LTS"]
        SSHD["sshd :22"]
        PERT["Scripts de perturbação<br/>unidades stress-ng · tc netem"]
        NODE["node-exporter<br/>rede do host :9100"]
        subgraph DC["Docker Compose · rede lab 172.30.0.0/24"]
            NGINX["nginx<br/>publicado em 10.10.10.1:8080"]
            API["api<br/>172.30.0.10:8000"]
            COL["collector"]
            BACK["prometheus · loki · tempo · grafana<br/>publicados somente em 127.0.0.1"]
        end
    end

    K6 -->|"HTTP · cabo"| NGINX
    PROBE -->|"HTTP · cabo"| NGINX
    ORCH -->|"SSH · cabo"| SSHD
    BROWSER --> TERM
    TERM -->|"SSH · cabo"| SSHD
    SSHD -->|"sudo restrito"| PERT
    SSHD -->|"túnel para 127.0.0.1"| BACK
    NGINX --> API --> COL --> BACK
    NODE -.->|scrape| BACK
    ROUTER -.-|Wi-Fi| TERM
    ROUTER -.-|Wi-Fi| SSHD
```

O notebook e o servidor são ligados por um cabo Ethernet dedicado (`10.10.10.2` ↔ `10.10.10.1`, sem gateway), que transporta a carga, a sonda e o SSH. O Wi-Fi é usado apenas para acesso à internet e atualizações, de modo que a sua variação de latência não afeta as medições. O NGINX e a unica porta de aplicacao publicada intencionalmente na rede dedicada.
O Node Exporter usa `network_mode: host` e a porta 9100 exige verificacao de escuta e firewall;
as interfaces administrativas sao acessiveis pelo tunel SSH.

---

## 2. Pipeline de telemetria

```mermaid
flowchart LR
    subgraph APP["contêiner api · SDK do OpenTelemetry"]
        SDK_T["TracerProvider<br/>BatchSpanProcessor"]
        SDK_M["MeterProvider<br/>exportação a cada 5 s"]
        SDK_L["LoggerProvider<br/>BatchLogRecordProcessor"]
    end

    subgraph COLL["OpenTelemetry Collector"]
        RCV["receiver otlp<br/>HTTP :4318"]
        PROC["processors<br/>memory_limiter → batch"]
        EXP_T["exporter<br/>otlp_grpc/tempo"]
        EXP_M["exporter prometheus<br/>:8889"]
        EXP_L["exporter<br/>otlp_http/loki"]
        SELF["métricas internas<br/>:8888"]
    end

    NODE["Node Exporter<br/>:9100"]
    TEMPO[("Tempo<br/>traces · 90 dias")]
    LOKI[("Loki<br/>logs · 90 dias")]
    PROM[("Prometheus<br/>métricas · 90 dias")]
    GRAF["Grafana"]

    SDK_T -->|OTLP/HTTP| RCV
    SDK_M -->|OTLP/HTTP| RCV
    SDK_L -->|OTLP/HTTP| RCV
    RCV --> PROC
    PROC -->|traces| EXP_T
    PROC -->|métricas| EXP_M
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

Traces e logs são **enviados** pelo Collector ao Tempo e ao Loki; as métricas são expostas pelo Collector e **coletadas** pelo Prometheus (*scrape*). No Grafana, o `trace_id` presente em cada log abre o trace correspondente no Tempo, e cada trace leva de volta aos seus logs.

---

## 3. Percurso de uma requisição

```mermaid
sequenceDiagram
    autonumber
    participant K6 as k6 (notebook)
    participant NG as NGINX
    participant API as Aplicação FastAPI
    participant COL as OTel Collector
    participant BE as Tempo · Loki · Prometheus

    K6->>NG: GET /work?n=20000 com o cabeçalho X-Run-ID
    NG->>API: encaminhada por uma conexão keepalive
    activate API
    Note over API: início do span de servidor GET /work<br/>run_id gravado como atributo do span
    API->>API: span filho validar_entrada
    API->>API: span filho calcular_hash (SHA-256 aplicado n vezes)
    Note over API: log request_completed emitido dentro do span<br/>com trace_id e span_id
    API-->>NG: 200 com n e digest
    deactivate API
    NG-->>K6: 200 com n e digest
    Note over NG: log de acesso em JSON com request_time e run_id
    Note over K6: sucesso somente se o status for 200 e o digest estiver correto
    API-)COL: spans, histograma de duração e logs em lotes (OTLP/HTTP)
    COL-)BE: traces para o Tempo, logs para o Loki, métricas expostas para scrape
```

O mesmo `trace_id` aparece no trace (Tempo) e no log (Loki) da requisição, e é isso que torna a correlação verificável. O `run_id` liga ambos à pasta da execução; ele nunca é usado como rótulo de métrica.

---

## 4. Fases de uma execução

```mermaid
flowchart TB
    subgraph LOAD["C0–C3 · cenários de carga · 240 s"]
        direction LR
        W1["Aquecimento<br/>60 s<br/>descartado"] --> M1["Fase útil<br/>180 s"]
    end

    subgraph PERT["C4–C7 · cenários de perturbação · 600 s (C7: 480 s)"]
        direction LR
        W2["Aquecimento<br/>60 s<br/>descartado"] --> B["Antes<br/>180 s"] --> D["Durante<br/>180 s de perturbação<br/>C7: 60 s com a API parada"] --> A["Depois<br/>180 s<br/>recuperação"]
    end

    LOAD ~~~ PERT
```

As requisições são atribuídas às fases pelo horário de conclusão. Nos cenários C4–C7, o início e o fim da perturbação são registrados pelo próprio servidor e alinhados aos dados do cliente com o deslocamento de relógio medido na execução. A recuperação é atingida na primeira janela de 30 s com P95 ≤ 1,2 × o P95 da fase *antes* e sem falhas, mantida por 60 s.

---

## 5. Orquestração de uma execução

```mermaid
sequenceDiagram
    participant OP as Operador
    participant OR as Orquestrador (WSL)
    participant GEN as k6, sonda e medidores
    participant SV as Servidor do laboratório

    OP->>OR: run_scenario.sh C4 r02 campaign
    OR->>OR: confere a árvore Git limpa e registra o commit
    OR->>SV: SSH: relógio, commit do servidor, serviços e estressores ativos
    alt deslocamento acima de 1 s, commits diferentes ou estressor ativo
        OR-->>OP: aborta antes de medir
    end
    OR->>OR: grava o manifest.json
    OR->>GEN: inicia ping, sonda e amostragem do notebook
    OR->>GEN: inicia o k6 (aquecimento e fases)
    opt C4 a C7, no início da fase durante
        OR->>SV: SSH sudo script tcc2-cpu / mem / net / apifail
        SV-->>OR: events-server.csv com início e fim no relógio do servidor
    end
    GEN-->>OR: fim do k6, 20 s de drenagem, sonda e medidores parados
    OR->>SV: SSH export_run.py: Prometheus, Loki, Tempo, contêineres, journal
    SV-->>OR: exportações copiadas para a pasta da execução
    OR->>OR: manifesto final, análise preliminar, notes.md, checksums.sha256
    OP->>OR: revisa a execução e registra a validade no notes.md
```

Cada execução produz uma pasta autocontida, `runs/<pilot|campaign>/<cenário>-<repetição>-<horário UTC>/`. Uma execução interrompida ou classificada como inválida é mantida e marcada, nunca apagada.

---

## 6. Fluxo de dados e evidências

```mermaid
flowchart LR
    RUN[("Pasta da execução<br/>manifesto · k6 bruto · sonda<br/>exportações do servidor · checksums")]
    BK[("Três cópias<br/>WSL · Windows + disco externo · nuvem")]
    AN["analyze_run.py<br/>phases.csv · windows.csv · summary.json"]
    CHK{"Execução válida?<br/>notes.md"}
    INV["Mantida e marcada como INVALIDA<br/>cenário repetido"]
    CONS["consolidate.py<br/>summary-runs.csv<br/>summary-scenarios.csv"]
    FIG["plot_load.py · plot_run.py<br/>figuras PNG 300 dpi"]
    IDX["evidence-index.csv"]
    ART["Artigo<br/>tabelas, figuras e apêndices"]

    RUN --> AN --> CHK
    CHK -->|sim| CONS --> FIG --> ART
    CHK -->|não| INV
    RUN -.->|"no mesmo dia"| BK
    CONS -.-> IDX
    FIG -.-> IDX
    IDX -.-> ART
```

Todo número do artigo deve ser rastreável até um arquivo: o índice de evidências registra o arquivo de origem, o script ou a consulta que o produziu e onde ele é utilizado.

---

## 7. Etapas de implementação e avaliação

```mermaid
flowchart LR
    subgraph PREP["Preparação"]
        direction TB
        S0["Etapa 0<br/>acesso, inventário e backup"] --> S1["Etapa 1<br/>rede cabeada, relógio UTC e Docker"] --> S2["Etapa 2<br/>mesmo commit nas duas máquinas"]
    end

    subgraph BUILD["Construção e integração"]
        direction TB
        S3["Etapa 3<br/>API atrás do NGINX e testes funcionais"] --> S4A["Etapa 4A<br/>instrumentação comprovada com o exporter de depuração"] --> S4B["Etapa 4B<br/>back-ends e prova de correlação log-trace"] --> S5["Etapa 5<br/>painéis, consultas e exportação"]
    end

    subgraph CAL["Calibração"]
        direction TB
        S6["Etapa 6<br/>pilotos: rampa de capacidade, cargas,<br/>metas e perturbações"] --> S7{{"Etapa 7<br/>protocolo v1 congelado<br/>commit e tag"}}
    end

    subgraph MEAS["Medição e análise"]
        direction TB
        S8["Etapa 8<br/>campanha: C0–C6 (+C7)<br/>3 blocos, 3 repetições"] --> S9["Etapa 9<br/>análise: SLIs × SLOs"] --> S10["Etapa 10<br/>reimplantação a partir do repositório"] --> S11["Etapa 11<br/>índice de evidências e figuras finais"]
    end

    S2 --> S3
    S5 --> S6
    S7 --> S8
    S7 -.->|"mudança solicitada"| V2["Protocolo v2<br/>motivo registrado"]
    V2 -.->|"repetir os cenários afetados"| S8
```

Uma etapa só começa depois que a anterior cumpre o seu critério de saída, registrado no diário de bordo. Metas, cargas e janelas são congeladas antes da campanha; qualquer mudança posterior gera uma nova versão do protocolo, em vez de alterar a anterior.
