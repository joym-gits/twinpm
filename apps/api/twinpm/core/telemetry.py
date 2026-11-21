"""OpenTelemetry tracing and Prometheus metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine

HTTP_REQUESTS = Counter(
    "twinpm_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "twinpm_http_request_duration_seconds", "HTTP request latency", ["method", "route"]
)
LLM_CALLS = Counter("twinpm_llm_calls_total", "LLM calls", ["purpose", "model", "status"])
LLM_TOKENS = Counter("twinpm_llm_tokens_total", "LLM tokens", ["purpose", "direction"])

_configured = False


def configure_tracing(app: FastAPI, engine: AsyncEngine, otlp_endpoint: str | None) -> None:
    """Instrument FastAPI, SQLAlchemy and httpx. Export only when an OTLP endpoint is set."""
    global _configured
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    if not _configured:
        provider = TracerProvider(resource=Resource.create({"service.name": "twinpm-api"}))
        if otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces"))
            )
        trace.set_tracer_provider(provider)
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        HTTPXClientInstrumentor().instrument()
        _configured = True
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz,metrics")


tracer = trace.get_tracer("twinpm")
