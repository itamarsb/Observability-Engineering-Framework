"""Configuracao do OpenTelemetry para a API do TCC2.

Este modulo configura explicitamente os tres provedores (traces, metricas e
logs) ANTES de o objeto FastAPI ser criado em main.py. Todos os sinais sao
exportados via OTLP/HTTP para o OpenTelemetry Collector (porta 4318).

Variaveis de ambiente usadas (definidas no compose.yaml):
  TELEMETRY_ENABLED               true/false (false = mede o custo da telemetria)
  OTEL_SERVICE_NAME               nome do servico (padrao: tcc2-api)
  APP_VERSION                     versao/commit da aplicacao
  OTEL_EXPORTER_OTLP_ENDPOINT     ex.: http://collector:4318
  OTEL_METRIC_EXPORT_INTERVAL     intervalo de exportacao de metricas em ms
  OTEL_SEMCONV_STABILITY_OPT_IN   "http" -> metrica estavel http.server.request.duration
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys

from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "tcc2-api")
APP_VERSION = os.getenv("APP_VERSION", "dev")
TELEMETRY_ENABLED = os.getenv("TELEMETRY_ENABLED", "true").strip().lower() == "true"

# Limites (em segundos) do histograma de duracao das requisicoes.
# Mais finos entre 2 ms e 50 ms porque /work leva ~10 ms por requisicao.
# AJUSTE NO PILOTO e CONGELE no protocolo (nao altere durante a campanha).
DURATION_BUCKETS_S = (
    0.002, 0.004, 0.006, 0.008, 0.010, 0.012, 0.015, 0.020, 0.025, 0.030,
    0.040, 0.050, 0.075, 0.100, 0.150, 0.200, 0.300, 0.500, 1.0, 2.0, 5.0,
)

_otel_logger: _logs.Logger | None = None


def _resource() -> Resource:
    return Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": APP_VERSION,
            "service.instance.id": socket.gethostname(),
            "deployment.environment.name": "lab",
        }
    )


def setup_telemetry() -> None:
    """Configura os provedores globais. Chamar uma unica vez, antes de criar o app."""
    global _otel_logger
    _setup_console_logging()
    if not TELEMETRY_ENABLED:
        logging.getLogger("tcc2.telemetry").warning("TELEMETRY_ENABLED=false: sem exportacao OTLP")
        return

    resource = _resource()

    # 1) Traces: amostragem padrao = 100% (ParentBased(ALWAYS_ON)).
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    # 2) Metricas: histograma com limites explicitos via View.
    interval_ms = int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "5000"))
    reader = PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=interval_ms)
    duration_view = View(
        instrument_name="http.server.request.duration",
        aggregation=ExplicitBucketHistogramAggregation(boundaries=DURATION_BUCKETS_S),
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader], views=[duration_view])
    metrics.set_meter_provider(meter_provider)

    # 3) Logs: API de logs do OpenTelemetry (o LoggingHandler do SDK esta depreciado).
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    _logs.set_logger_provider(logger_provider)
    _otel_logger = _logs.get_logger("tcc2.api", APP_VERSION)


def instrument_app(app) -> None:
    """Cria o span de servidor de cada requisicao e a metrica http.server.request.duration."""
    if not TELEMETRY_ENABLED:
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    # exclude_spans remove os spans internos "http send/receive" do ASGI, que
    # poluem o trace sem acrescentar informacao ao experimento.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health", exclude_spans=["receive", "send"])


def emit_event(name: str, attributes: dict, severity: str = "INFO") -> None:
    """Emite um evento estruturado (log) dentro do contexto do span ativo.

    O trace_id e o span_id sao anexados automaticamente pelo SDK a partir do
    contexto atual. Tambem escreve uma linha JSON no stdout (plano B e depuracao).
    """
    span_ctx = trace.get_current_span().get_span_context()
    trace_id = format(span_ctx.trace_id, "032x") if span_ctx.is_valid else ""
    span_id = format(span_ctx.span_id, "016x") if span_ctx.is_valid else ""
    line = {"event": name, "severity": severity, "trace_id": trace_id, "span_id": span_id, **attributes}
    print(json.dumps(line, ensure_ascii=False), file=sys.stdout, flush=True)

    if _otel_logger is None:
        return
    number = {
        "DEBUG": _logs.SeverityNumber.DEBUG,
        "INFO": _logs.SeverityNumber.INFO,
        "WARN": _logs.SeverityNumber.WARN,
        "ERROR": _logs.SeverityNumber.ERROR,
    }.get(severity, _logs.SeverityNumber.INFO)
    _otel_logger.emit(
        body=name,
        severity_number=number,
        severity_text=severity,
        attributes={"event": name, **attributes},
    )


def _setup_console_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
