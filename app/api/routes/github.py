"""
GitHub connection routes (mounted at /auth/github).

OAuth flow
──────────
1. GET  /authorize?return_to=/onboarding       (signed-in user)
       Creates a single-use nonce, signs {user, nonce, return_to, expiry}
       into the OAuth ``state`` and returns GitHub's authorisation URL.
2. GET  /callback?code&state                   (browser, redirected by GitHub)
       Verifies the signature and expiry, consumes the nonce, exchanges the
       code for a token and parks it — encrypted — under a one-time
       ``handoff`` code for five minutes, then redirects the browser to the
       dashboard's /github/complete page.
3. POST /complete {handoff}                    (signed-in user, from the dashboard)
       Attaches the token to the account ONLY if the signed-in user is the
       one who started the flow.

Why the hand-off: GitHub's callback carries no session.  Without step 3 an
attacker could start the flow on their own account and trick a victim into
finishing it, attaching the victim's GitHub token to the attacker's account.

Other endpoints
───────────────
DELETE /             disconnect (revokes TrueAI's grant on GitHub)
GET    /repos        repositories the connection can access (repo picker)
GET    /branches     branches of a repository (branch picker)
POST   /repo         set the default repository (+ optional branch)
POST   /branch       set the default branch
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import require_jwt_user
from app.core.config import settings
from app.core.errors import DatabaseError, GitHubError
from app.core.logging import get_logger
from app.core.rate_limit import ip_rate_limit, user_rate_limit
from app.core.security import safe_relative_path
from app.schemas.account import BranchSelectRequest, GitHubCompleteRequest, RepoSelectRequest
from app.services import redis as redis_svc
from app.services import supabase as db
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.github import client as gh

logger = get_logger(__name__)

router = APIRouter()

_GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"
_STATE_TTL_SECONDS = 900
_HANDOFF_TTL_SECONDS = 300
_RETURN_PATHS = ("/onboarding", "/integrations", "/settings")


def _callback_url() -> str:
    return f"{settings.BASE_URL}/auth/github/callback"


def _github_error(exc: GitHubError) -> HTTPException:
    if exc.status in (401,):
        return HTTPException(status.HTTP_409_CONFLICT, "GitHub rejected the stored token. Reconnect GitHub.")
    if exc.status == 404:
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if exc.status == 403:
        return HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    if exc.status == 400:
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return HTTPException(status.HTTP_502_BAD_GATEWAY, "GitHub is not responding right now. Please try again.")


def _require_connection(user_id: str) -> gh.GitHubConnection:
    try:
        connection = gh.load_connection(user_id)
    except DatabaseError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not load your GitHub connection.")
    if connection is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect GitHub first.")
    return connection


# ================================================================== #
# OAuth                                                                #
# ================================================================== #

@router.get("/authorize", summary="Start connecting GitHub")
def github_authorize(
    return_to: Optional[str] = Query(default=None, max_length=200),
    redirect_uri: Optional[str] = Query(default=None, max_length=500, include_in_schema=False),
    user_id: str = Depends(require_jwt_user),
    _limit: None = Depends(user_rate_limit("github-authorize", 20, 3600)),
) -> Dict[str, str]:
    # ``redirect_uri`` was accepted by older dashboard builds; only its path is honoured.
    if return_to is None and redirect_uri:
        from urllib.parse import urlsplit

        return_to = urlsplit(redirect_uri).path
    destination = safe_relative_path(return_to, _RETURN_PATHS, "/integrations")

    nonce = secrets.token_urlsafe(24)
    if not redis_svc.set_value(f"oauth-nonce:{nonce}", user_id, _STATE_TTL_SECONDS):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "GitHub connection is temporarily unavailable.")
    state = _sign_state({"u": user_id, "n": nonce, "r": destination, "e": int(time.time()) + _STATE_TTL_SECONDS})
    query = urlencode(
        {
            "client_id": settings.GITHUB_CLIENT_ID,
            "scope": settings.GITHUB_OAUTH_SCOPES,
            "state": state,
            "redirect_uri": _callback_url(),
            "allow_signup": "true",
        }
    )
    logger.info("github_authorize: started | user_id=%s", user_id)
    return {"auth_url": f"{_GITHUB_AUTHORIZE_URL}?{query}"}


@router.get("/callback", summary="GitHub OAuth callback", dependencies=[Depends(ip_rate_limit("github-callback", 30, 60))])
async def github_callback(
    code: Optional[str] = Query(default=None, max_length=200),
    state: Optional[str] = Query(default=None, max_length=2000),
    error: Optional[str] = Query(default=None, max_length=100),
) -> RedirectResponse:
    payload = _verify_state(state) if state else None
    destination = payload["r"] if payload else "/integrations"

    if error:
        return _to_frontend(destination, github_error=error if error == "access_denied" else "github_error")
    if not payload or not code:
        return _to_frontend(destination, github_error="invalid_state")

    # Redis calls are blocking; run them off the event loop (this route is async for the httpx calls).
    owner = await run_in_threadpool(redis_svc.pop_value, f"oauth-nonce:{payload['n']}")
    if owner != payload["u"]:
        logger.warning("github_callback: nonce missing, reused or mismatched")
        return _to_frontend(destination, github_error="invalid_state")

    token, scopes = await _exchange_code(code)
    if not token:
        return _to_frontend(destination, github_error="exchange_failed")
    username, github_user_id = await _fetch_github_user(token)
    if not username:
        return _to_frontend(destination, github_error="profile_failed")

    handoff = secrets.token_urlsafe(32)
    stored = json.dumps(
        {
            "user_id": payload["u"],
            "token": encrypt_secret(token),
            "username": username,
            "github_user_id": github_user_id,
            "scopes": scopes or "",
            "return_to": destination,
        }
    )
    if not await run_in_threadpool(redis_svc.set_value, f"oauth-handoff:{handoff}", stored, _HANDOFF_TTL_SECONDS):
        return _to_frontend(destination, github_error="unavailable")
    query = urlencode({"handoff": handoff, "return_to": destination})
    return RedirectResponse(f"{settings.FRONTEND_URL}/github/complete?{query}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/complete", summary="Attach the authorised GitHub account to the signed-in user")
def github_complete(body: GitHubCompleteRequest, user_id: str = Depends(require_jwt_user)) -> Dict[str, Any]:
    raw = redis_svc.pop_value(f"oauth-handoff:{body.handoff}")
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This GitHub authorisation has expired. Please connect again.")
    try:
        data = json.loads(raw)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This GitHub authorisation is invalid. Please connect again.")
    if data.get("user_id") != user_id:
        logger.warning("github_complete: hand-off belongs to a different user | user_id=%s", user_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This GitHub authorisation was started by a different account.")

    try:
        token = decrypt_secret(data["token"])
    except Exception:  # the encryption key changed between the callback and this request
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This GitHub authorisation has expired. Please connect again.")
    try:
        existing = db.get_github_row(user_id)
        db.upsert_github_row(
            {
                "user_id": user_id,
                "access_token": encrypt_secret(token),
                "github_username": data["username"],
                "github_user_id": data.get("github_user_id"),
                "scopes": data.get("scopes") or None,
                "repo_name": (existing or {}).get("repo_name"),
                "branch_name": (existing or {}).get("branch_name"),
            }
        )
    except DatabaseError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not save the GitHub connection. Please try again.")
    logger.info("github_complete: connected | user_id=%s", user_id)
    return {"github_username": data["username"], "return_to": data.get("return_to") or "/integrations"}


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Disconnect GitHub")
def github_disconnect(user_id: str = Depends(require_jwt_user)) -> None:
    try:
        connection = gh.load_connection(user_id)
        if connection:
            gh.revoke_oauth_grant(connection.token)
        db.delete_github_row(user_id)
    except DatabaseError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not disconnect GitHub right now.")
    logger.info("github_disconnect: disconnected | user_id=%s", user_id)


# ================================================================== #
# Repository & branch selection                                        #
# ================================================================== #

@router.get("/repos", summary="Repositories available to the connected account")
def github_repos(
    q: str = Query(default="", max_length=100),
    user_id: str = Depends(require_jwt_user),
    _limit: None = Depends(user_rate_limit("github-repos", 60, 60)),
) -> Dict[str, Any]:
    connection = _require_connection(user_id)
    try:
        return {"repositories": gh.list_repositories(connection.token, q)}
    except GitHubError as exc:
        raise _github_error(exc)


@router.get("/branches", summary="Branches of a repository")
def github_branches(
    repo: str = Query(..., max_length=201),
    user_id: str = Depends(require_jwt_user),
    _limit: None = Depends(user_rate_limit("github-branches", 60, 60)),
) -> Dict[str, Any]:
    from app.schemas.account import validate_repo_full_name

    try:
        repo = validate_repo_full_name(repo)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    connection = _require_connection(user_id)
    try:
        return gh.list_branches(connection.token, repo)
    except GitHubError as exc:
        raise _github_error(exc)


@router.post("/repo", summary="Set the default repository")
def set_github_repo(body: RepoSelectRequest, user_id: str = Depends(require_jwt_user)) -> Dict[str, Any]:
    connection = _require_connection(user_id)
    try:
        access = gh.get_repository_access(connection.token, body.repo_name)
        branch = body.branch_name
        if branch and not gh.branch_exists(connection.token, access["full_name"], branch):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Branch '{branch}' does not exist in {access['full_name']}.")
    except GitHubError as exc:
        raise _github_error(exc)
    if access.get("archived"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This repository is archived; TrueAI cannot open pull requests on it.")

    try:
        db.save_repo_mapping(user_id, None, access["full_name"], branch or access["default_branch"])
    except DatabaseError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not save the repository.")
    return {
        "status": "ok",
        "repo_name": access["full_name"],
        "branch_name": branch or access["default_branch"],
        "can_push": access["can_push"],
    }


@router.post("/branch", summary="Set the default branch")
def set_github_branch(body: BranchSelectRequest, user_id: str = Depends(require_jwt_user)) -> Dict[str, Any]:
    try:
        mapping = db.get_default_mapping(user_id)
    except DatabaseError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not load your repository.")
    if not mapping:
        raise HTTPException(status.HTTP_409_CONFLICT, "Choose a repository first.")
    connection = _require_connection(user_id)
    try:
        if not gh.branch_exists(connection.token, mapping["repo_full_name"], body.branch_name):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Branch '{body.branch_name}' does not exist in {mapping['repo_full_name']}."
            )
    except GitHubError as exc:
        raise _github_error(exc)
    try:
        db.save_repo_mapping(user_id, None, mapping["repo_full_name"], body.branch_name)
    except DatabaseError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not save the branch.")
    return {"status": "ok", "branch_name": body.branch_name}


# ================================================================== #
# Helpers                                                              #
# ================================================================== #

def _sign_state(payload: Dict[str, Any]) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new((settings.secret("API_KEY_SECRET") or "").encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _verify_state(state: str) -> Optional[Dict[str, Any]]:
    try:
        encoded, signature = state.rsplit(".", 1)
        expected = hmac.new((settings.secret("API_KEY_SECRET") or "").encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if not isinstance(payload, dict) or int(payload.get("e", 0)) < time.time():
            return None
        payload["r"] = safe_relative_path(payload.get("r"), _RETURN_PATHS, "/integrations")
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _to_frontend(path: str, **params: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.FRONTEND_URL}{path}?{urlencode(params)}", status_code=status.HTTP_303_SEE_OTHER)


async def _exchange_code(code: str) -> tuple[Optional[str], Optional[str]]:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                _GITHUB_TOKEN_URL,
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.secret("GITHUB_CLIENT_SECRET"),
                    "code": code,
                    "redirect_uri": _callback_url(),
                },
                headers={"Accept": "application/json"},
            )
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("GitHub code exchange failed: %s", type(exc).__name__)
        return None, None
    if "error" in data or not data.get("access_token"):
        logger.warning("GitHub code exchange rejected: %s", data.get("error"))
        return None, None
    return data["access_token"], data.get("scope")


async def _fetch_github_user(token: str) -> tuple[Optional[str], Optional[int]]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                _GITHUB_USER_URL,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("GitHub profile fetch failed: %s", type(exc).__name__)
        return None, None
    return data.get("login"), data.get("id")
