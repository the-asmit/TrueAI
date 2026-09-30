"""
Account, profile and API key routes.

Endpoints
─────────
GET    /auth/me                  profile + connection status used by the dashboard
POST   /auth/profile             save display name
DELETE /auth/account             delete the account and every piece of data
GET    /auth/api-keys            list keys (prefix, name, last used — never the secret)
POST   /auth/api-keys            create a key; returns the raw key and webhook URL ONCE
DELETE /auth/api-keys/{key_id}   revoke a key
GET    /auth/user/webhook-url    webhook base URL (the full URL is only shown at creation)

Account-level actions require a signed-in session (JWT); an API key can
never create keys or delete an account.
"""

from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import require_jwt_user
from app.auth.api_keys import generate_api_key, webhook_url_for
from app.core.config import settings
from app.core.errors import DatabaseError
from app.core.logging import get_logger
from app.core.rate_limit import user_rate_limit
from app.schemas.account import ApiKeyCreateRequest, ProfileUpdateRequest
from app.services import supabase as db

logger = get_logger(__name__)

router = APIRouter()


def _unavailable(action: str) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Could not {action} right now. Please try again.")


# ================================================================== #
# Profile & status                                                     #
# ================================================================== #

@router.get("/me", summary="Current user, onboarding and integration status")
def get_me(user_id: str = Depends(require_jwt_user)) -> Dict[str, Any]:
    from app.core.llm import configured_agents

    try:
        profile = db.get_profile(user_id) or {}
        github = db.get_github_row(user_id) or {}
        default_repo = db.get_default_mapping(user_id) or {}
        sentry = db.get_sentry_integration(user_id) or {}
        active_keys = db.count_active_api_keys(user_id)
    except DatabaseError:
        raise _unavailable("load your account")

    github_connected = bool(github.get("access_token"))
    try:
        agents = configured_agents()
    except Exception:
        agents = {}
    return {
        "user_id": user_id,
        "full_name": profile.get("full_name"),
        "github_connected": github_connected,
        "github_username": github.get("github_username") if github_connected else None,
        "github_repo": default_repo.get("repo_full_name"),
        "github_branch": default_repo.get("branch"),
        "has_api_key": active_keys > 0,
        "sentry": {
            "org_slug": sentry.get("org_slug"),
            "has_auth_token": bool(sentry.get("auth_token_enc")),
            "has_webhook_secret": bool(sentry.get("webhook_secret_enc")),
        },
        "onboarding_complete": bool(profile.get("full_name") and github_connected and default_repo and active_keys > 0),
        "agents": agents,
        "auto_pr_threshold": settings.CONFIDENCE_AUTO_PR_THRESHOLD,
    }


@router.post("/profile", summary="Save display name")
def update_profile(body: ProfileUpdateRequest, user_id: str = Depends(require_jwt_user)) -> Dict[str, Any]:
    try:
        db.upsert_profile(user_id, body.full_name)
    except DatabaseError:
        raise _unavailable("save your profile")
    return {"status": "ok", "full_name": body.full_name}


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT, summary="Delete account and all data")
def delete_account(
    user_id: str = Depends(require_jwt_user),
    _limit: None = Depends(user_rate_limit("delete-account", 5, 3600)),
) -> None:
    from app.services.github.client import load_connection, revoke_oauth_grant

    try:
        connection = load_connection(user_id)
        if connection:
            revoke_oauth_grant(connection.token)
        db.delete_user_data(user_id)
        db.delete_auth_user(user_id)
    except DatabaseError:
        raise _unavailable("delete your account")
    logger.info("delete_account: account deleted | user_id=%s", user_id)


# ================================================================== #
# API keys                                                             #
# ================================================================== #

@router.get("/api-keys", summary="List API keys")
def list_api_keys(user_id: str = Depends(require_jwt_user)) -> List[Dict[str, Any]]:
    try:
        return db.list_api_keys(user_id)
    except DatabaseError:
        raise _unavailable("load your API keys")


@router.post("/api-keys", status_code=status.HTTP_201_CREATED, summary="Create an API key")
def create_api_key(
    body: ApiKeyCreateRequest = ApiKeyCreateRequest(),
    user_id: str = Depends(require_jwt_user),
    _limit: None = Depends(user_rate_limit("create-api-key", 20, 3600)),
) -> Dict[str, Any]:
    try:
        if db.count_active_api_keys(user_id) >= settings.MAX_ACTIVE_API_KEYS:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"You already have {settings.MAX_ACTIVE_API_KEYS} active keys. Revoke one before creating another.",
            )
        raw_key, hashed_key, prefix = generate_api_key()
        row = db.insert_api_key(user_id, hashed_key, prefix, body.name)
    except DatabaseError:
        raise _unavailable("create an API key")

    logger.info("create_api_key: key created | user_id=%s | prefix=%s", user_id, prefix)
    return {
        "id": row["id"],
        "name": row.get("name"),
        "key_prefix": prefix,
        "created_at": row.get("created_at"),
        "raw_key": raw_key,
        "webhook_url": webhook_url_for(raw_key),
        "message": "Copy this now — the key cannot be shown again.",
    }


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke an API key")
def revoke_api_key(key_id: UUID, user_id: str = Depends(require_jwt_user)) -> None:
    try:
        revoked = db.revoke_api_key(user_id, str(key_id))
    except DatabaseError:
        raise _unavailable("revoke the key")
    if not revoked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found.")
    logger.info("revoke_api_key: revoked | user_id=%s | key_id=%s", user_id, key_id)


@router.get("/user/webhook-url", summary="Sentry webhook endpoint details")
def get_webhook_url(user_id: str = Depends(require_jwt_user)) -> Dict[str, Any]:
    """
    The complete webhook URL embeds a secret key, which is only ever shown
    when the key is created.  This endpoint returns the base URL and whether
    an active key exists, so the dashboard can guide the user.
    """
    try:
        keys = [k for k in db.list_api_keys(user_id) if k.get("is_active")]
    except DatabaseError:
        raise _unavailable("load webhook details")
    return {
        "webhook_base_url": f"{settings.BASE_URL}/webhook/sentry",
        "has_active_key": bool(keys),
        "key_prefix": keys[0]["key_prefix"] if keys else None,
    }
