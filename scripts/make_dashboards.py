#!/usr/bin/env python3
"""Gera os JSON dos paineis 01 a 04 do Grafana (provisionados por arquivo).

Os paineis ficam versionados no Git. Nao os altere so pela interface: altere este
script (ou o JSON exportado), faca commit e reinicie o Grafana.
Uso: python3 scripts/make_dashboards.py config/grafana/dashboards
"""

import json
import os
import sys

PROM = {"type": "prometheus", "uid": "prom"}
LOKI = {"type": "loki", "uid": "loki"}
TEMPO = {"type": "tempo", "uid": "tempo"}
SEL = 'job="tcc2-api",http_route="/work"'


def ts(title, exprs, unit, x, y, w=12, h=8, ds=PROM, desc=""):
    return {
        "type": "timeseries", "title": title, "description": desc, "datasource": ds,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [{"refId": chr(65 + i), "datasource": ds, "expr": e, "legendFormat": lg}
                    for i, (e, lg) in enumerate(exprs)],
        "fieldConfig": {"defaults": {"unit": unit, "decimals": 1,
                                     "custom": {"lineWidth": 2, "fillOpacity": 0, "spanNulls": False}},
                        "overrides": []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                    "tooltip": {"mode": "multi", "sort": "none"}},
    }


def dash(uid, title, panels, templating=None):
    return {
        "uid": uid, "title": title, "tags": ["tcc2"], "timezone": "utc", "editable": False,
        "schemaVersion": 39, "version": 1, "refresh": "", "graphTooltip": 1,
        "time": {"from": "now-30m", "to": "now"},
        "templating": {"list": templating or []}, "annotations": {"list": []},
        "panels": panels,
    }


RUN_VAR = [{"type": "textbox", "name": "run_id", "label": "run_id (prefixo)", "query": "", "current": {"value": ""}}]

d01 = dash("tcc2-01-servico", "TCC2 01 - Servico HTTP (visao do servidor)", [
    ts("Vazao em /work (RPS)", [(f"sum(rate(http_server_request_duration_seconds_count{{{SEL}}}[1m]))", "RPS")],
       "reqps", 0, 0, desc="Requisicoes concluidas por segundo, medidas pelo servidor (janela de 1 min)."),
    ts("Latencia do servidor P95 e P99 (ms)", [
        (f"1000 * histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket{{{SEL}}}[1m])))", "P95"),
        (f"1000 * histogram_quantile(0.99, sum by (le) (rate(http_server_request_duration_seconds_bucket{{{SEL}}}[1m])))", "P99")],
       "ms", 12, 0, desc="Estimativa por histograma (buckets). A fonte primaria da latencia do cliente e o k6."),
    ts("Respostas 5xx (%)", [(f"100 * (sum(rate(http_server_request_duration_seconds_count{{{SEL},http_response_status_code=~\"5..\"}}[1m])) or vector(0)) / sum(rate(http_server_request_duration_seconds_count{{{SEL}}}[1m]))", "5xx %")],
       "percent", 0, 8, desc="Sem trafego o valor fica vazio (sem amostras), nao zero."),
    ts("Requisicoes por codigo de status (RPS)", [('sum by (http_response_status_code) (rate(http_server_request_duration_seconds_count{job="tcc2-api"}[1m]))', "{{http_response_status_code}}")],
       "reqps", 12, 8),
])

d02 = dash("tcc2-02-recursos", "TCC2 02 - Recursos do servidor (host fisico)", [
    ts("CPU do host (%)", [('100 * (1 - avg(rate(node_cpu_seconds_total{job="node",mode="idle"}[1m])))', "CPU total"),
                           ('100 * avg(rate(node_cpu_seconds_total{job="node",mode="iowait"}[1m]))', "iowait")],
       "percent", 0, 0),
    ts("RAM usada (%) a partir de MemAvailable", [('100 * (1 - node_memory_MemAvailable_bytes{job="node"} / node_memory_MemTotal_bytes{job="node"})', "RAM usada")],
       "percent", 12, 0),
    ts("Memoria disponivel e swap usada", [('node_memory_MemAvailable_bytes{job="node"}', "MemAvailable"),
                                          ('node_memory_SwapTotal_bytes{job="node"} - node_memory_SwapFree_bytes{job="node"}', "Swap usada")],
       "bytes", 0, 8),
    ts("Carga do sistema (load 1 min)", [('node_load1{job="node"}', "load1")], "short", 12, 8),
    ts("Trafego de rede do host", [('sum by (device) (rate(node_network_receive_bytes_total{job="node",device!~"lo|veth.*|br-.*|docker.*"}[1m]))', "rx {{device}}"),
                                   ('sum by (device) (rate(node_network_transmit_bytes_total{job="node",device!~"lo|veth.*|br-.*|docker.*"}[1m]))', "tx {{device}}")],
       "Bps", 0, 16),
    ts("Temperatura maxima (sensores)", [('max(node_hwmon_temp_celsius{job="node"})', "max")], "celsius", 12, 16),
])

d03 = dash("tcc2-03-integridade", "TCC2 03 - Integridade da telemetria", [
    ts("Alvos raspados (up = 1)", [("up", "{{job}}")], "short", 0, 0,
       desc="up indica sucesso do scrape, NAO disponibilidade da API."),
    ts("Itens aceitos pelo Collector (por s)", [("rate(otelcol_receiver_accepted_spans[1m])", "spans"),
                                               ("rate(otelcol_receiver_accepted_log_records[1m])", "logs"),
                                               ("rate(otelcol_receiver_accepted_metric_points[1m])", "pontos de metrica")],
       "short", 12, 0),
    ts("Recusas e falhas de envio do Collector", [
        ("rate(otelcol_receiver_refused_spans[1m]) + rate(otelcol_receiver_refused_log_records[1m]) + rate(otelcol_receiver_refused_metric_points[1m])", "recusados"),
        ('sum(rate({__name__=~"otelcol_exporter_send_failed_.*"}[1m]))', "falhas de envio")],
       "short", 0, 8, desc="'Sem dados' em falhas de envio e normal: a serie so existe apos a 1a falha."),
    ts("Fila dos exporters do Collector", [("otelcol_exporter_queue_size", "{{exporter}}")], "short", 12, 8),
])

d04 = dash("tcc2-04-investigacao", "TCC2 04 - Investigacao (logs e traces por run_id)", [
    {
        "type": "logs", "title": "Eventos da API (filtre pelo run_id)", "datasource": LOKI,
        "gridPos": {"h": 12, "w": 24, "x": 0, "y": 0},
        "targets": [{"refId": "A", "datasource": LOKI,
                     "expr": '{service_name="tcc2-api"} | run_id=~"${run_id}.*"'}],
        "options": {"showTime": True, "wrapLogMessage": True, "enableLogDetails": True,
                    "sortOrder": "Descending", "dedupStrategy": "none"},
    },
    {
        "type": "table", "title": "Traces da execucao (TraceQL)", "datasource": TEMPO,
        "gridPos": {"h": 10, "w": 24, "x": 0, "y": 12},
        "targets": [{"refId": "A", "datasource": TEMPO, "queryType": "traceql", "limit": 20,
                     "query": '{ span.tcc2.run_id =~ "${run_id}.*" }'}],
    },
    ts("Erros registrados nos logs (eventos/s)", [('sum(rate({service_name="tcc2-api"} | severity_text="ERROR" [1m]))', "ERROR")],
       "short", 0, 22, w=24, ds=LOKI),
], templating=RUN_VAR)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "config/grafana/dashboards"
    os.makedirs(out, exist_ok=True)
    for name, d in [("01-servico-http", d01), ("02-recursos-host", d02),
                    ("03-integridade-telemetria", d03), ("04-investigacao", d04)]:
        with open(os.path.join(out, f"{name}.json"), "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=2, ensure_ascii=False)
    print(f"4 paineis gerados em {out}")


if __name__ == "__main__":
    main()
