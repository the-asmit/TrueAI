"""
GitHub API client helpers for TrueAI.

All functions here are synchronous (PyGithub is synchronous); async callers
wrap them in ``asyncio.to_thread``.

Error contract
──────────────
Every GitHub failure is raised as :class:`~app.core.errors.GitHubError`
carrying the HTTP status and a ``retryable`` flag (429 / 5xx / network are
retryable; 401 / 403 / 404 / 422 are not).  The access token is never logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from cryptography.fernet import InvalidToken
from github import Auth, BadCredentialsException, Github, GithubException, RateLimitExceededException
from github.Repository import Repository

from app.core.config import settings
from app.core.errors import GitHubError
from app.core.logging import get_logger

logger = get_logger(__name__)

_API_TIMEOUT_SECONDS = 20


# ------------------------------------------------------------------ #
# Connection lookup                                                    #
# ------------------------------------------------------------------ #

@dataclass(frozen=True)
class GitHubConnection:
    token: str
    username: Optional[str]


def load_connection(user_id: str) -> Optional[GitHubConnection]:
    """
    Return the user's decrypted GitHub connection, or None if not connected.

    Legacy plaintext tokens are transparently re-encrypted on first use.
    A token that cannot be decrypted (e.g. the encryption key was changed)
    is treated as "not connected" so the user is prompted to reconnect.
    """
    from app.services import supabase as db
    from app.services.crypto import decrypt_github_token, encrypt_secret

    row = db.get_github_row(user_id)
    if not row or not row.get("access_token"):
        return None
    try:
        token, legacy = decrypt_github_token(row["access_token"])
    except InvalidToken:
        logger.error("GitHub token for user_id=%s cannot be decrypted — user must reconnect.", user_id)
        return None
    if legacy:
        db.update_github_row(user_id, {"access_token": encrypt_secret(token)})
    return GitHubConnection(token=token, username=row.get("github_username"))


# ------------------------------------------------------------------ #
# Client factory & error mapping                                       #
# ------------------------------------------------------------------ #

def get_github_client(access_token: str) -> Github:
    if not access_token:
        raise GitHubError("GitHub is not connected.", status=401)
    return Github(auth=Auth.Token(access_token), per_page=100, retry=2, timeout=_API_TIMEOUT_SECONDS)


def to_github_error(exc: Exception, action: str) -> GitHubError:
    """Translate a PyGithub/network exception into a GitHubError with a user-facing message."""
    if isinstance(exc, GitHubError):
        return exc
    if isinstance(exc, BadCredentialsException):
        return GitHubError("GitHub rejected the token (expired or revoked). Reconnect GitHub.", status=401)
    if isinstance(exc, RateLimitExceededException):
        return GitHubError("GitHub API rate limit reached. TrueAI will retry later.", status=429, retryable=True)
    if isinstance(exc, GithubException):
        status = exc.status or 0
        detail = ""
        if isinstance(exc.data, dict):
            detail = str(exc.data.get("message") or "")[:200]
        if status == 403:
            message = f"GitHub denied access while trying to {action}. {detail}".strip()
        elif status == 404:
            message = f"Not found on GitHub while trying to {action} (repository missing or no access)."
        else:
            message = f"GitHub returned HTTP {status} while trying to {action}. {detail}".strip()
        return GitHubError(message, status=status)
    if isinstance(exc, (httpx.HTTPError, ConnectionError, TimeoutError, OSError)):
        return GitHubError(f"Network error while trying to {action}.", status=None, retryable=True)
    return GitHubError(f"Unexpected error while trying to {action}: {type(exc).__name__}", status=None, retryable=False)


def get_repository(access_token: str, repo_full_name: str) -> Repository:
    validate_repo_name(repo_full_name)
    try:
        return get_github_client(access_token).get_repo(repo_full_name)
    except Exception as exc:
        raise to_github_error(exc, f"open {repo_full_name}") from exc


def validate_repo_name(repo_full_name: str) -> None:
    parts = (repo_full_name or "").split("/")
    if len(parts) != 2 or not all(parts) or any(p in (".", "..") for p in parts):
        raise GitHubError(f"Repository must be in 'owner/repo' format, got {repo_full_name!r}.", status=400)


# ------------------------------------------------------------------ #
# Repository & branch discovery (dashboard pickers)                    #
# ------------------------------------------------------------------ #

def list_repositories(access_token: str, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
    """Repositories the token can see, most recently pushed first, filtered by *query*."""
    needle = query.strip().lower()
    results: List[Dict[str, Any]] = []
    try:
        user = get_github_client(access_token).get_user()
        repos = user.get_repos(sort="pushed", affiliation="owner,collaborator,organization_member")
        for scanned, repo in enumerate(repos):
            if scanned >= 500 or len(results) >= limit:
                break
            if needle and needle not in repo.full_name.lower():
                continue
            permissions = repo.permissions
            results.append(
                {
                    "full_name": repo.full_name,
                    "private": repo.private,
                    "default_branch": repo.default_branch,
                    "can_push": bool(permissions and (permissions.push or permissions.admin)),
                    "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
                }
            )
    except Exception as exc:
        raise to_github_error(exc, "list repositories") from exc
    return results


def get_repository_access(access_token: str, repo_full_name: str) -> Dict[str, Any]:
    """Confirm the token can read *repo_full_name* and report whether it can push."""
    repo = get_repository(access_token, repo_full_name)
    try:
        permissions = repo.permissions
        return {
            "full_name": repo.full_name,
            "default_branch": repo.default_branch,
            "private": repo.private,
            "archived": repo.archived,
            "can_push": bool(permissions and (permissions.push or permissions.admin)),
        }
    except Exception as exc:
        raise to_github_error(exc, f"read {repo_full_name}") from exc


def list_branches(access_token: str, repo_full_name: str, limit: int = 100) -> Dict[str, Any]:
    repo = get_repository(access_token, repo_full_name)
    try:
        names = [branch.name for _, branch in zip(range(limit), repo.get_branches())]
        return {"default_branch": repo.default_branch, "branches": names}
    except Exception as exc:
        raise to_github_error(exc, f"list branches of {repo_full_name}") from exc


def branch_exists(access_token: str, repo_full_name: str, branch: str) -> bool:
    repo = get_repository(access_token, repo_full_name)
    try:
        repo.get_branch(branch)
        return True
    except GithubException as exc:
        if exc.status == 404:
            return False
        raise to_github_error(exc, f"read branch {branch}") from exc


# ------------------------------------------------------------------ #
# OAuth grant revocation                                               #
# ------------------------------------------------------------------ #

def revoke_oauth_grant(access_token: str) -> bool:
    """
    Revoke TrueAI's OAuth grant for this token so GitHub no longer lists
    the app as authorised.  Best effort — returns False on failure.
    """
    try:
        response = httpx.request(
            "DELETE",
            f"https://api.github.com/applications/{settings.GITHUB_CLIENT_ID}/grant",
            auth=(settings.GITHUB_CLIENT_ID, settings.secret("GITHUB_CLIENT_SECRET") or ""),
            json={"access_token": access_token},
            headers={"Accept": "application/vnd.github+json"},
            timeout=10.0,
        )
        return response.status_code in (204, 404)
    except httpx.HTTPError as exc:
        logger.warning("revoke_oauth_grant failed: %s", type(exc).__name__)
        return False
