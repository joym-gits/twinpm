"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from twinpm.api import health
from twinpm.api.v1 import api_router
from twinpm.config import get_settings
from twinpm.core.errors import install_error_handlers
from twinpm.core.logging import configure_logging, get_logger
from twinpm.core.middleware import RequestContextMiddleware
from twinpm.core.telemetry import configure_tracing
from twinpm.db.session import get_engine

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log.info("startup", env=settings.env, demo_mode=settings.effective_demo_mode)
    from twinpm.agents.runtime import shutdown_agent_runtime, startup_agent_runtime

    await startup_agent_runtime()
    yield
    await shutdown_agent_runtime()
    await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(
        title="TwinPM API",
        version="0.1.0",
        description=(
            "TwinPM doesn't just answer questions about your program. "
            "It runs it the way you would, and shows its reasoning every time."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["content-type", "x-csrf-token", "x-request-id", "authorization"],
    )
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router, prefix="/api/v1")
    configure_tracing(app, get_engine(), settings.otel_exporter_otlp_endpoint)
    return app


app = create_app()
