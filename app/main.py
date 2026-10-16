"""API experimental do TCC2 (objeto observado pelo framework).

Rotas:
  GET /health            -> 200 {"status": "ok"}
  GET /work?n=20000      -> 200 {"n": n, "digest": "<hex>"}  (calculo deterministico)
  GET /controlled-error  -> 503 (somente com ENABLE_TEST_ROUTES=true; fora da campanha)

O algoritmo de /work e fixo: value = b"tcc2"; repetir n vezes value = sha256(value);
retornar value.hex(). A mesma entrada sempre produz o mesmo digest.
"""

from __future__ import annotations

import hashlib
import os
import time

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from telemetry import APP_VERSION, emit_event, instrument_app, setup_telemetry

# A telemetria precisa ser configurada ANTES de criar o objeto FastAPI.
setup_telemetry()

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

N_MIN, N_MAX = 1, 100_000
ENABLE_TEST_ROUTES = os.getenv("ENABLE_TEST_ROUTES", "false").strip().lower() == "true"
SEED = b"tcc2"

tracer = trace.get_tracer("tcc2.api", APP_VERSION)
app = FastAPI(title="TCC2 Observability API", version=APP_VERSION)


@app.middleware("http")
async def request_completed_log(request: Request, call_next):
    """Mede a duracao e emite o evento request_completed no contexto do span."""
    start = time.perf_counter()
    run_id = request.headers.get("x-run-id", "")
    span = trace.get_current_span()
    if run_id and span.is_recording():
        # run_id vira atributo do span (busca no Tempo), NUNCA rotulo de metrica.
        span.set_attribute("tcc2.run_id", run_id)
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        if request.url.path != "/health":
            route = request.scope.get("route")
            emit_event(
                "request_completed",
                {
                    "route": getattr(route, "path", request.url.path),
                    "method": request.method,
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 3),
                    "run_id": run_id,
                },
                severity="ERROR" if status_code >= 500 else "INFO",
            )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/work")
def work(n: int = 20000) -> dict:
    # Rota sincrona (def): o trabalho bloqueante roda no pool de threads,
    # e nao diretamente no event loop.
    with tracer.start_as_current_span("validar_entrada") as span:
        span.set_attribute("tcc2.n", n)
        if not (N_MIN <= n <= N_MAX):
            span.set_status(Status(StatusCode.ERROR, "n fora do intervalo"))
            raise HTTPException(status_code=422, detail=f"n deve estar entre {N_MIN} e {N_MAX}")
    with tracer.start_as_current_span("calcular_hash") as span:
        span.set_attribute("tcc2.n", n)
        value = SEED
        for _ in range(n):
            value = hashlib.sha256(value).digest()
    return {"n": n, "digest": value.hex()}


@app.get("/controlled-error")
def controlled_error():
    if not ENABLE_TEST_ROUTES:
        raise HTTPException(status_code=404, detail="Not Found")
    span = trace.get_current_span()
    span.set_status(Status(StatusCode.ERROR, "erro controlado"))
    emit_event("controlled_error", {"route": "/controlled-error", "error_code": "CONTROLLED_ERROR"}, severity="ERROR")
    return JSONResponse(status_code=503, content={"error": "controlled_error", "code": "CONTROLLED_ERROR"})


# Cria o span de servidor HTTP e a metrica http.server.request.duration.
instrument_app(app)
