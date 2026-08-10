import typing
"""
FastAPI application entry point.

Defines:
  - The ASGI application with metadata
  - The lifespan handler (startup/shutdown)
  - Route registration
  - Global exception handlers
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from restockiq.api.routers import (
    health_router,
    merchants_router,
    recommendations_router,
    signals_router,
)
from restockiq.container import build_container
from restockiq.shared_kernel.errors import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
    RestockIQError,
)

logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> typing.AsyncGenerator[None, None]:  
    """
    Application startup / shutdown handler.

    Startup:
      1. Build the DI container (creates engine + session factory).
      2. Log the configured environment.

    Shutdown:
      1. Dispose the database connection pool.
    """
    container = build_container()
    logger.info("RestockIQ starting — environment: %s", container.settings.app_env)
    yield
    await container.engine.dispose()
    logger.info("RestockIQ shutdown complete")


# ── Application ───────────────────────────────────────────────────────────────


app = FastAPI(
    title="RestockIQ",
    summary="Cash-constrained restocking advisor for nanostore owners",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(health_router.router)
app.include_router(merchants_router.router, prefix="/api/v1")
app.include_router(signals_router.router, prefix="/api/v1")
app.include_router(recommendations_router.router, prefix="/api/v1")


# ── Exception handlers ────────────────────────────────────────────────────────


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc), "type": "not_found"},
    )


@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc), "type": "conflict"},
    )


@app.exception_handler(DomainValidationError)
async def domain_validation_handler(request: Request, exc: DomainValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "type": "domain_validation_error"},
    )


@app.exception_handler(RestockIQError)
async def restockiq_error_handler(request: Request, exc: RestockIQError) -> JSONResponse:
    logger.exception("Unhandled RestockIQ domain error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred.", "type": "internal_error"},
    )
