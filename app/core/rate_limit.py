"""
Redis-backed fixed-window rate limiting shared by every API process.

Used as FastAPI dependencies, e.g.::

    @router.post("/x", dependencies=[Depends(user_rate_limit("reanalyze", 20, 3600))])

Buckets are keyed by an identity (user id, hashed API key or client IP),
never by a raw secret.  When Redis is unavailable the limiter fails open.
"""

from __future__ import annotations

import hashlib
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings
from app.services import redis as redis_svc


def client_ip(request: Request) -> str:
    """Resolve the caller IP, honouring X-Forwarded-For only when configured."""
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def enforce(bucket: str, identity: str, limit: int, window_seconds: int) -> None:
    """Raise HTTP 429 when *identity* exceeds *limit* per window for *bucket*."""
    count = redis_svc.incr_window(f"{bucket}:{_digest(identity)}", window_seconds)
    if count is not None and count > limit:
        retry_after = redis_svc.window_reset_seconds(window_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down and try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )


def ip_rate_limit(bucket: str, limit: int, window_seconds: int = 60) -> Callable[[Request], None]:
    def _dependency(request: Request) -> None:
        enforce(bucket, client_ip(request), limit, window_seconds)

    return _dependency


def user_rate_limit(bucket: str, limit: int, window_seconds: int = 60) -> Callable[..., None]:
    # Imported lazily to avoid a circular import with the dependencies module.
    from app.api.dependencies import require_current_user

    def _dependency(user_id: str = Depends(require_current_user)) -> None:
        enforce(bucket, user_id, limit, window_seconds)

    return _dependency


def default_user_limit() -> Callable[..., None]:
    return user_rate_limit("api", settings.API_RATE_LIMIT_PER_MINUTE, 60)
