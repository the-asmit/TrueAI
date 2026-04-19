"""
TrueAI FastAPI application entry point.

Startup sequence
────────────────
1. Lifespan handler eagerly initialises every singleton (Supabase, Redis,
   Anthropic LLM) so the first request never pays the cold-start penalty
   and misconfigured credentials surface at boot time, not mid-request.
2. Routers are registered with path prefixes and OpenAPI tags.
3. CORS, request-ID injection, and global exception handlers are attached.

Running locally
───────────────
    uvicorn main:app --reload --port 8000

Running in production
─────────────────────
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.auth import router as auth_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.webhook import router as webhook_router
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ================================================================== #
# Lifespan — startup & shutdown                                       #
# ================================================================== #

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialise all external connections on startup; release on shutdown.

    Eager initialisation means:
    - The first HTTP request is not slowed by connection setup.
    - Misconfigured credentials (bad API key, wrong Redis URL) raise an
      error immediately at startup rather than returning 500s at runtime.
    """
    logger.info("TrueAI starting up | base_url=%s", settings.BASE_URL)

    # Supabase client — validates URL and service-role key
    try:
        from app.services.supabase import get_supabase
        get_supabase()
        logger.info("Supabase connection: OK")
    except Exception as exc:
        logger.error("Supabase connection FAILED at startup: %s", exc)
        raise

    # Redis client — validates REDIS_URL and pings the server
    try:
        from app.services.redis import get_redis
        get_redis()
        logger.info("Redis connection: OK")
    except Exception as exc:
        logger.error("Redis connection FAILED at startup: %s", exc)
        raise

    # Anthropic LLM client — validates API key format
    try:
        from app.core.llm import get_llm
        get_llm()
        logger.info("Anthropic LLM client: OK")
    except Exception as exc:
        logger.error("Anthropic LLM client FAILED at startup: %s", exc)
        raise

    logger.info("TrueAI startup complete — ready to serve requests.")
    yield

    # ---- Shutdown ------------------------------------------------- #
    logger.info("TrueAI shutting down — releasing connections.")
    try:
        from app.services.redis import reset_redis
        reset_redis()
    except Exception as exc:
        logger.warning("Redis shutdown error (non-fatal): %s", exc)

    try:
        from app.core.llm import reset_llm
        reset_llm()
    except Exception as exc:
        logger.warning("LLM shutdown error (non-fatal): %s", exc)

    logger.info("TrueAI shutdown complete.")


# ================================================================== #
# Application factory                                                  #
# ================================================================== #

app = FastAPI(
    title="TrueAI",
    description=(
        "AI-powered incident analysis system. "
        "Receives Sentry webhooks, analyses errors with Claude, "
        "fetches relevant source from GitHub, generates fixes, "
        "and opens pull requests automatically."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ================================================================== #
# Middleware                                                           #
# ================================================================== #

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten per-environment via env var if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    Inject a unique X-Request-ID header into every request/response pair.

    If the client supplies X-Request-ID we echo it back; otherwise we
    generate a UUID.  This allows end-to-end tracing across load balancers,
    the FastAPI layer, Celery workers, and log aggregators.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    response.headers["X-Request-ID"] = request_id

    logger.info(
        "%s %s | status=%d | duration=%.1fms | request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    return response


# ================================================================== #
# Exception handlers                                                   #
# ================================================================== #

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return structured 422 responses for Pydantic validation failures."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": exc.body,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Catch-all for any unhandled exception.

    Returns a generic 500 — never leaks internal error details (stack
    traces, file paths, query strings) to API consumers.  The full error
    is logged server-side with request_id for correlation.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        "Unhandled exception | request_id=%s | path=%s | error=%s — %s",
        request_id,
        request.url.path,
        type(exc).__name__,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal server error occurred.",
            "request_id": request_id,
        },
    )


# ================================================================== #
# Routers                                                              #
# ================================================================== #

app.include_router(webhook_router,   prefix="/webhook",   tags=["Webhooks"])
app.include_router(incidents_router, prefix="/incidents", tags=["Incidents"])
app.include_router(auth_router,      prefix="/auth",      tags=["Auth"])


# ================================================================== #
# Built-in health and info endpoints                                   #
# ================================================================== #

@app.get(
    "/health",
    summary="Liveness probe",
    tags=["Health"],
    response_model=Dict[str, Any],
)
async def health_check() -> Dict[str, Any]:
    """
    Lightweight liveness probe for load balancers and Kubernetes probes.

    Does NOT check downstream dependencies (Redis, Supabase) — those are
    checked at startup.  Use ``/health/ready`` for a readiness probe that
    verifies all connections.
    """
    return {"status": "ok", "service": "trueai", "version": "1.0.0"}


@app.get(
    "/health/ready",
    summary="Readiness probe",
    tags=["Health"],
    response_model=Dict[str, Any],
)
async def readiness_check() -> JSONResponse:
    """
    Readiness probe that verifies Redis and Supabase are reachable.

    Returns 200 when all dependencies are healthy, 503 otherwise.
    Safe to call frequently — uses existing connection pools, no new sockets.
    """
    checks: Dict[str, str] = {}
    healthy = True

    try:
        from app.services.redis import get_redis
        get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        healthy = False

    try:
        from app.services.supabase import get_supabase
        # Minimal query to verify the DB connection is live
        get_supabase().table("incidents").select("id").limit(1).execute()
        checks["supabase"] = "ok"
    except Exception as exc:
        checks["supabase"] = f"error: {exc}"
        healthy = False

    http_status = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=http_status,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )
