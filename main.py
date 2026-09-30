"""
TrueAI FastAPI application entry point.

Startup sequence
────────────────
1. Logging is configured before anything else is imported.
2. The lifespan handler validates configuration that would otherwise fail
   mid-request: the encryption key, every agent's LLM provider credentials,
   and connectivity to Supabase and Redis.
3. Routers, middleware (security headers, request ids, CORS, trusted hosts)
   and exception handlers are attached.

Running locally
───────────────
    uvicorn main:app --reload --port 8000

Running in production
─────────────────────
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers
"""

from __future__ import annotations

from app.core.logging import configure_logging

configure_logging("api")

import re  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from typing import Any, Dict  # noqa: E402

from fastapi import Depends, FastAPI, Request, status  # noqa: E402
from fastapi.encoders import jsonable_encoder  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.middleware.trustedhost import TrustedHostMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from app.api.routes.auth import router as auth_router  # noqa: E402
from app.api.routes.github import router as github_router  # noqa: E402
from app.api.routes.incidents import router as incidents_router  # noqa: E402
from app.api.routes.integrations import router as integrations_router  # noqa: E402
from app.api.routes.webhook import router as webhook_router  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.logging import get_logger, request_id_var  # noqa: E402
from app.core.rate_limit import default_user_limit  # noqa: E402

logger = get_logger(__name__)

VERSION = "2.0.0"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


# ================================================================== #
# Lifespan — startup & shutdown                                        #
# ================================================================== #

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TrueAI %s starting | env=%s | base_url=%s", VERSION, settings.ENV, settings.BASE_URL)

    from app.core.llm import configured_agents, validate_llm_configuration
    from app.services import redis as redis_svc
    from app.services import supabase as db
    from app.services.crypto import validate_key

    validate_key()
    logger.info("Encryption key: OK")

    validate_llm_configuration()
    for agent, model in configured_agents().items():
        logger.info("Agent %-13s -> %s", agent, model)
    from app.core.llm import check_models_available

    for warning in await run_in_threadpool(check_models_available):
        logger.error("LLM model check: %s", warning)

    if not await run_in_threadpool(db.ping):
        raise RuntimeError("Supabase is unreachable — check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    logger.info("Supabase: OK")

    if not await run_in_threadpool(redis_svc.ping):
        raise RuntimeError("Redis is unreachable at REDIS_URL — start Redis before the API.")
    logger.info("Redis: OK")

    if not settings.SENTRY_WEBHOOK_SECRET:
        logger.info(
            "No global SENTRY_WEBHOOK_SECRET: webhook signatures are verified per user when they save "
            "a signing secret in Integrations; API keys still authenticate every delivery."
        )
    logger.info("TrueAI startup complete.")
    yield

    logger.info("TrueAI shutting down.")
    redis_svc.reset_redis()


# ================================================================== #
# Application                                                          #
# ================================================================== #

app = FastAPI(
    title="TrueAI",
    description=(
        "Multi-agent incident response: receives Sentry errors, analyses them with a team of "
        "AI agents, and opens reviewed fix pull requests on GitHub."
    ),
    version=VERSION,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=lifespan,
)

if settings.ALLOWED_HOSTS and "*" not in settings.ALLOWED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
    max_age=600,
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Assign a request id, time the request, and add security headers."""
    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if _REQUEST_ID_RE.match(supplied) else uuid.uuid4().hex
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers.setdefault("Cache-Control", "no-store")
    if settings.BASE_URL.startswith("https://"):
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

    logger.info(
        "%s %s | status=%d | duration=%.1fms | request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
        request_id,
    )
    return response


# ================================================================== #
# Exception handlers                                                   #
# ================================================================== #

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 with field errors only — never echo submitted values (they may be secrets)."""
    errors = [
        {"loc": error.get("loc"), "msg": error.get("msg"), "type": error.get("type")}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Generic 500 — details stay in the server log, correlated by request id."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        "Unhandled exception | request_id=%s | path=%s | error=%s",
        request_id,
        request.url.path,
        type(exc).__name__,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred.", "request_id": request_id},
    )


# ================================================================== #
# Routers                                                              #
# ================================================================== #

_user_limit = [Depends(default_user_limit())]

app.include_router(webhook_router, prefix="/webhook", tags=["Webhooks"])
app.include_router(incidents_router, prefix="/incidents", tags=["Incidents"], dependencies=_user_limit)
app.include_router(auth_router, prefix="/auth", tags=["Account"], dependencies=_user_limit)
app.include_router(github_router, prefix="/auth/github", tags=["GitHub"])
app.include_router(integrations_router, prefix="/integrations", tags=["Integrations"], dependencies=_user_limit)


# ================================================================== #
# Health                                                               #
# ================================================================== #

@app.get("/health", summary="Liveness probe", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    return {"status": "ok", "service": "trueai", "version": VERSION}


@app.get("/health/ready", summary="Readiness probe", tags=["Health"])
async def readiness_check() -> JSONResponse:
    from app.services import redis as redis_svc
    from app.services import supabase as db

    checks = {
        "redis": "ok" if await run_in_threadpool(redis_svc.ping) else "error",
        "supabase": "ok" if await run_in_threadpool(db.ping) else "error",
    }
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )
