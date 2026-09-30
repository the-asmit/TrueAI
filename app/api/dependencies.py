"""
FastAPI dependency injection for TrueAI.

Authentication model
────────────────────
Every protected route resolves to a ``user_id`` via one of:

1. Bearer JWT  (``Authorization: Bearer <supabase access token>``) — the dashboard.
2. API key     (``X-API-Key: tai_…``) — scripts and CI calling the API.

The Sentry webhook uses the ``?key=`` query parameter instead (Sentry cannot
send custom headers) and resolves it inside the webhook route.

These dependencies are synchronous on purpose: they perform blocking
network I/O (JWKS fetch, database lookup) and FastAPI runs sync
dependencies in its thread pool, keeping the event loop free.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import DatabaseError
from app.core.logging import get_logger

logger = get_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> Optional[str]:
    """Return the caller's user_id, None when no credential was sent, or raise 401 for a bad one."""
    if credentials is not None:
        from app.auth.jwt import get_user_id_from_token

        return get_user_id_from_token(credentials.credentials)

    if x_api_key:
        from app.auth.api_keys import resolve_api_key

        try:
            user_id = resolve_api_key(x_api_key.strip())
        except DatabaseError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication is temporarily unavailable.")
        if user_id:
            return user_id
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked API key.")

    return None


def require_current_user(user_id: Optional[str] = Depends(get_current_user)) -> str:
    """Enforce authentication on a route (401 when no credential is present)."""
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


def require_jwt_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme)) -> str:
    """
    Require a signed-in *user session* (JWT).  Used for account-level actions
    (connecting GitHub, managing keys, deleting the account) that an API key
    must never be able to perform.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to perform this action.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    from app.auth.jwt import get_user_id_from_token

    return get_user_id_from_token(credentials.credentials)
