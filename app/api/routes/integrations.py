"""
Integration settings routes (mounted at /integrations).

Repository mappings
───────────────────
Route incidents from different Sentry projects to different repositories.
The mapping without a project (set via /auth/github/repo) is the default
used for any project without its own mapping.

    GET    /integrations/repositories
    POST   /integrations/repositories        {sentry_project, repo_full_name, branch?}
    DELETE /integrations/repositories/{id}

Sentry settings
───────────────
Optional per-user Sentry connection.  The auth token lets TrueAI fetch the
full event when a webhook has no stack trace; the webhook secret enables
signature verification of incoming webhooks.  Secrets are encrypted at rest
and never returned.

    GET    /integrations/sentry
    PUT    /integrations/sentry              {org_slug?, base_url?, auth_token?, webhook_secret?}
    DELETE /integrations/sentry
"""

from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import require_jwt_user
from app.core.config import settings
from app.core.errors import DatabaseError, GitHubError, SentryAPIError
from app.core.logging import get_logger
from app.core.security import validate_external_https_url
from app.schemas.account import RepoMappingRequest, SentrySettingsRequest
from app.services import supabase as db
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.github import client as gh
from app.services.sentry import verify_credentials

logger = get_logger(__name__)

router = APIRouter()


def _db_unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The database is temporarily unavailable. Please try again.")


# ================================================================== #
# Repository mappings                                                  #
# ================================================================== #

@router.get("/repositories", summary="List repository mappings")
def list_repositories(user_id: str = Depends(require_jwt_user)) -> List[Dict[str, Any]]:
    try:
        return db.list_repo_mappings(user_id)
    except DatabaseError:
        raise _db_unavailable()


@router.post("/repositories", status_code=status.HTTP_201_CREATED, summary="Map a Sentry project to a repository")
def create_repository_mapping(body: RepoMappingRequest, user_id: str = Depends(require_jwt_user)) -> Dict[str, Any]:
    try:
        connection = gh.load_connection(user_id)
    except DatabaseError:
        raise _db_unavailable()
    if connection is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect GitHub first.")
    try:
        access = gh.get_repository_access(connection.token, body.repo_full_name)
        if body.branch and not gh.branch_exists(connection.token, access["full_name"], body.branch):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Branch '{body.branch}' does not exist in {access['full_name']}.")
    except GitHubError as exc:
        detail = str(exc) if exc.status in (400, 403, 404) else "GitHub is not responding right now."
        raise HTTPException(status.HTTP_400_BAD_REQUEST if exc.status in (400, 403, 404) else status.HTTP_502_BAD_GATEWAY, detail)
    try:
        row = db.save_repo_mapping(user_id, body.sentry_project, access["full_name"], body.branch or access["default_branch"])
    except DatabaseError:
        raise _db_unavailable()
    return {**row, "can_push": access["can_push"]}


@router.delete("/repositories/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a mapping")
def delete_repository_mapping(mapping_id: UUID, user_id: str = Depends(require_jwt_user)) -> None:
    try:
        deleted = db.delete_repo_mapping(user_id, str(mapping_id))
    except DatabaseError:
        raise _db_unavailable()
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mapping not found.")


# ================================================================== #
# Sentry settings                                                      #
# ================================================================== #

@router.get("/sentry", summary="Sentry connection settings")
def get_sentry_settings(user_id: str = Depends(require_jwt_user)) -> Dict[str, Any]:
    try:
        row = db.get_sentry_integration(user_id) or {}
    except DatabaseError:
        raise _db_unavailable()
    return {
        "org_slug": row.get("org_slug"),
        "base_url": row.get("base_url") or settings.SENTRY_API_BASE_URL,
        "has_auth_token": bool(row.get("auth_token_enc")),
        "has_webhook_secret": bool(row.get("webhook_secret_enc")),
        "webhook_base_url": f"{settings.BASE_URL}/webhook/sentry",
        "updated_at": row.get("updated_at"),
    }


@router.put("/sentry", summary="Save Sentry connection settings")
def save_sentry_settings(body: SentrySettingsRequest, user_id: str = Depends(require_jwt_user)) -> Dict[str, Any]:
    try:
        current = db.get_sentry_integration(user_id) or {}
    except DatabaseError:
        raise _db_unavailable()

    base_url = current.get("base_url") or settings.SENTRY_API_BASE_URL
    if body.base_url is not None:
        try:
            base_url = validate_external_https_url(body.base_url or settings.SENTRY_API_BASE_URL, settings.SENTRY_ALLOWED_HOSTS)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Sentry URL rejected: {exc}")

    org_slug = body.org_slug if body.org_slug is not None else current.get("org_slug")
    row: Dict[str, Any] = {"user_id": user_id, "org_slug": org_slug or None, "base_url": base_url}

    token_enc = current.get("auth_token_enc")
    if body.auth_token is not None:
        token_enc = encrypt_secret(body.auth_token) if body.auth_token else None
    if body.webhook_secret is not None:
        row["webhook_secret_enc"] = encrypt_secret(body.webhook_secret) if body.webhook_secret else None
    row["auth_token_enc"] = token_enc

    # A token is only useful together with an organisation — verify the pair works.
    if token_enc and (body.auth_token or body.org_slug is not None or body.base_url is not None):
        if not org_slug:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter your Sentry organisation slug to use an auth token.")
        try:
            verify_credentials(base_url, org_slug, decrypt_secret(token_enc))
        except SentryAPIError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    try:
        db.upsert_sentry_integration(row)
    except DatabaseError:
        raise _db_unavailable()
    logger.info("save_sentry_settings | user_id=%s | org=%s", user_id, org_slug)
    return get_sentry_settings(user_id)


@router.delete("/sentry", status_code=status.HTTP_204_NO_CONTENT, summary="Remove Sentry settings")
def delete_sentry_settings(user_id: str = Depends(require_jwt_user)) -> None:
    try:
        db.delete_sentry_integration(user_id)
    except DatabaseError:
        raise _db_unavailable()
