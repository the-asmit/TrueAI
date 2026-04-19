"""
Authentication routes for TrueAI.

Endpoints
─────────
POST   /auth/api-keys              — generate a new API key (shows raw once)
DELETE /auth/api-keys/{key_id}     — revoke an API key
GET    /auth/github/authorize      — begin GitHub OAuth flow
GET    /auth/github/callback       — complete GitHub OAuth flow
GET    /auth/me                    — return the authenticated user's info

GitHub OAuth flow
─────────────────
1. Client (browser) calls GET /auth/github/authorize?redirect_uri=<frontend_url>
   The user must be authenticated (Supabase JWT or API key).
   Returns a redirect URL the client must follow in the browser.

2. User authenticates on GitHub and is redirected to:
   GET /auth/github/callback?code=<github_code>&state=<signed_state>

3. The callback handler:
   a. Verifies the signed state (contains user_id + timestamp + HMAC).
   b. Exchanges the code for a GitHub access token via httpx.
   c. Fetches the authenticated GitHub user's login and ID.
   d. Upserts the token record in Supabase (on_conflict=user_id).
   e. Redirects the browser to the frontend success URL.

State parameter security
────────────────────────
The OAuth state is a Base64-encoded JSON blob signed with HMAC-SHA256
(keyed on API_KEY_SECRET).  This prevents CSRF: a forged callback with a
tampered state will fail HMAC verification.  The state also carries a
15-minute expiry timestamp.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.dependencies import require_current_user
from app.auth.api_keys import generate_api_key, mask_key_for_logging
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"
_GITHUB_SCOPES = "repo,read:user"
_STATE_TTL_SECONDS = 900   # 15 minutes


# ================================================================== #
# API key management                                                   #
# ================================================================== #

@router.post(
    "/api-keys",
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new API key",
)
async def create_api_key(
    user_id: str = Depends(require_current_user),
) -> Dict[str, Any]:
    """
    Generate a new API key for the authenticated user.

    The raw key is returned **once only** — it is never stored in the
    database and cannot be recovered after this response.  Store it
    immediately in a secrets manager.

    Returns:
        ``raw_key``    — the secret; show to user once and discard.
        ``key_prefix`` — first 10 chars; safe to display in dashboards.
    """
    raw_key, hashed_key = generate_api_key()

    try:
        from app.services.supabase import get_supabase

        response = (
            get_supabase()
            .table("api_keys")
            .insert({
                "user_id": user_id,
                "key_hash": hashed_key,
                "key_prefix": raw_key[:10],   # for display in UI
                "is_active": True,
            })
            .execute()
        )
        rows = response.data or []
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to persist API key.",
            )
        key_id = rows[0].get("id")

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "create_api_key: DB error | user_id=%s | error=%s", user_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create API key.",
        )

    logger.info(
        "create_api_key: new key created | user_id=%s | key_prefix=%s",
        user_id,
        mask_key_for_logging(raw_key),
    )

    return {
        "id": key_id,
        "raw_key": raw_key,          # shown once only
        "key_prefix": raw_key[:10],  # safe to cache
        "message": (
            "Store this key immediately — it will not be shown again. "
            "Use it as: X-API-Key: <raw_key>  or  ?key=<raw_key>"
        ),
    }


@router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
)
async def revoke_api_key(
    key_id: str,
    user_id: str = Depends(require_current_user),
) -> None:
    """
    Revoke (soft-delete) an API key by setting is_active = False.

    The key record is retained for audit purposes.  Future requests using
    this key will receive 401.
    """
    try:
        from app.services.supabase import get_supabase

        response = (
            get_supabase()
            .table("api_keys")
            .update({"is_active": False})
            .eq("id", key_id)
            .eq("user_id", user_id)   # ownership check
            .execute()
        )
        rows = response.data or []
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key {key_id} not found or not owned by you.",
            )

        logger.info(
            "revoke_api_key: key_id=%s revoked | user_id=%s", key_id, user_id
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "revoke_api_key: DB error | key_id=%s | error=%s", key_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke API key.",
        )


# ================================================================== #
# GitHub OAuth                                                         #
# ================================================================== #

@router.get(
    "/github/authorize",
    summary="Begin GitHub OAuth flow",
)
async def github_authorize(
    redirect_uri: Optional[str] = Query(
        default=None,
        description="Frontend URL to redirect to after OAuth completes.",
    ),
    user_id: str = Depends(require_current_user),
) -> Dict[str, str]:
    """
    Return the GitHub OAuth authorisation URL.

    The client must redirect the browser to ``auth_url``.  After the user
    grants access, GitHub redirects to /auth/github/callback.
    """
    state = _encode_oauth_state(user_id=user_id, redirect_uri=redirect_uri)

    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "scope": _GITHUB_SCOPES,
        "state": state,
        "redirect_uri": f"{settings.BASE_URL}/auth/github/callback",
    }
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    auth_url = f"{_GITHUB_AUTHORIZE_URL}?{query_string}"

    logger.info(
        "github_authorize: initiated | user_id=%s", user_id
    )
    return {"auth_url": auth_url}


@router.get(
    "/github/callback",
    summary="Complete GitHub OAuth flow",
)
async def github_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
) -> RedirectResponse:
    """
    Handle the GitHub OAuth callback.

    Exchanges the authorisation code for an access token, fetches the
    user's GitHub profile, stores the token in Supabase, and redirects
    the browser to the configured frontend URL.
    """
    # ---- GitHub returned an error ---------------------------------- #
    if error:
        logger.warning(
            "github_callback: GitHub returned error '%s': %s",
            error,
            error_description,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub OAuth error: {error_description or error}",
        )

    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'code' or 'state' query parameters.",
        )

    # ---- Verify state -------------------------------------------- #
    state_data = _decode_oauth_state(state)
    if state_data is None:
        logger.warning("github_callback: invalid or expired OAuth state.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state is invalid or expired. Please try again.",
        )

    user_id: str = state_data["user_id"]
    redirect_uri: Optional[str] = state_data.get("redirect_uri")

    # ---- Exchange code for access token -------------------------- #
    access_token, token_scope = await _exchange_github_code(code)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to obtain GitHub access token.",
        )

    # ---- Fetch GitHub user profile ------------------------------- #
    github_username, github_user_id = await _fetch_github_user(access_token)
    if not github_username:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch GitHub user profile.",
        )

    # ---- Persist token ------------------------------------------ #
    try:
        from app.services.supabase import store_github_token

        store_github_token({
            "user_id": user_id,
            "access_token": access_token,
            "token_type": "bearer",
            "scope": token_scope,
            "github_username": github_username,
            "github_user_id": github_user_id,
            "is_active": True,
        })
    except Exception as exc:
        logger.error(
            "github_callback: failed to store token | user_id=%s | error=%s",
            user_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub authentication succeeded but token storage failed.",
        )

    logger.info(
        "github_callback: token stored | user_id=%s | github_username=%s...",
        user_id,
        github_username[:4] if len(github_username) >= 4 else "****",
    )

    # ---- Redirect to frontend ------------------------------------ #
    destination = redirect_uri or settings.BASE_URL
    return RedirectResponse(
        url=f"{destination}?github_connected=true",
        status_code=status.HTTP_302_FOUND,
    )


# ================================================================== #
# Current user info                                                    #
# ================================================================== #

@router.get(
    "/me",
    summary="Get authenticated user info",
)
async def get_me(
    user_id: str = Depends(require_current_user),
) -> Dict[str, Any]:
    """Return basic profile info for the authenticated user."""
    try:
        from app.services.supabase import get_supabase

        # Check if GitHub is connected
        gh_response = (
            get_supabase()
            .table("github_tokens")
            .select("github_username, repo_name, created_at")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        github_row = (gh_response.data or [None])[0]

        return {
            "user_id": user_id,
            "github_connected": github_row is not None,
            "github_username": (github_row or {}).get("github_username"),
            "github_repo": (github_row or {}).get("repo_name"),
        }

    except Exception as exc:
        logger.error("get_me: error | user_id=%s | error=%s", user_id, exc)
        return {"user_id": user_id, "github_connected": False}


# ================================================================== #
# OAuth state helpers                                                  #
# ================================================================== #

def _encode_oauth_state(user_id: str, redirect_uri: Optional[str] = None) -> str:
    """
    Return a signed, Base64-encoded JSON blob for use as the OAuth state.

    Format: base64url(json) + "." + hmac_prefix_16_chars
    """
    payload = {
        "user_id": user_id,
        "ts": int(time.time()),
        "redirect_uri": redirect_uri,
    }
    raw = json.dumps(payload, separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    sig = hmac.new(
        settings.API_KEY_SECRET.encode("utf-8"),
        encoded.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:16]
    return f"{encoded}.{sig}"


def _decode_oauth_state(state: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode an OAuth state string.

    Returns the payload dict or None if the signature is invalid, the
    timestamp is expired, or the string is malformed.
    """
    try:
        encoded, sig = state.rsplit(".", 1)
        expected_sig = hmac.new(
            settings.API_KEY_SECRET.encode("utf-8"),
            encoded.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:16]

        if not hmac.compare_digest(sig, expected_sig):
            return None

        # Re-pad Base64
        padding = 4 - len(encoded) % 4
        padded = encoded + "=" * (padding % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())

        if time.time() - payload.get("ts", 0) > _STATE_TTL_SECONDS:
            return None

        return payload

    except Exception:
        return None


# ================================================================== #
# GitHub API helpers                                                   #
# ================================================================== #

async def _exchange_github_code(code: str) -> tuple[Optional[str], Optional[str]]:
    """
    Exchange an OAuth authorisation code for a GitHub access token.

    Returns (access_token, scope) or (None, None) on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                _GITHUB_TOKEN_URL,
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": f"{settings.BASE_URL}/auth/github/callback",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

        if "error" in data:
            logger.error(
                "_exchange_github_code: GitHub error '%s': %s",
                data.get("error"),
                data.get("error_description"),
            )
            return None, None

        return data.get("access_token"), data.get("scope")

    except Exception as exc:
        logger.error("_exchange_github_code: request failed: %s", exc)
        return None, None


async def _fetch_github_user(
    access_token: str,
) -> tuple[Optional[str], Optional[int]]:
    """
    Fetch the authenticated GitHub user's login and numeric ID.

    Returns (username, user_id) or (None, None) on failure.
    The access_token is never logged.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                _GITHUB_USER_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            response.raise_for_status()
            data = response.json()

        return data.get("login"), data.get("id")

    except Exception as exc:
        logger.error("_fetch_github_user: request failed: %s", exc)
        return None, None
