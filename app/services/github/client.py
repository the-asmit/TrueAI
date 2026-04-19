"""
GitHub API client factory and repository accessor for TrueAI.

Uses PyGithub (``PyGithub`` package) which wraps the GitHub REST API v3.
The client is stateless — a new ``Github`` instance is created per-call
(each instance manages its own connection pool via urllib3) so there is
no singleton; callers pass the access token on every call.

Error handling contract
───────────────────────
Every raised exception is converted to an :class:`~fastapi.HTTPException`
with a semantically correct status code:

  401 → expired or revoked GitHub token
  403 → insufficient scope or secondary rate limit (abuse detection)
  404 → repository not found or no read permission
  429 → primary rate limit exceeded
  502 → all other GitHub API errors (upstream failure)

The raw ``access_token`` is **never** written to any log record.  Only the
first 4 characters of the username are logged where attribution is needed.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from github import Auth, Github, GithubException, RateLimitExceededException
from github.Repository import Repository

from app.core.logging import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------ #
# Client factory                                                       #
# ------------------------------------------------------------------ #

def get_github_client(access_token: str) -> Github:
    """
    Return an authenticated :class:`github.Github` instance.

    The ``Github`` object wraps a ``urllib3`` connection pool internally.
    PyGithub handles retries for transient network errors automatically.

    Args:
        access_token: A valid GitHub OAuth token, fine-grained PAT, or
                      GitHub App installation token.  This value is **never**
                      logged.

    Returns:
        A :class:`github.Github` instance ready for API calls.

    Raises:
        :class:`fastapi.HTTPException` (401) if the token is obviously
        malformed (empty string).
    """
    if not access_token or not access_token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub access token is missing.",
        )

    return Github(
        auth=Auth.Token(access_token),
        per_page=100,          # maximise items per paginated request
        retry=3,               # urllib3 retry count for transient errors
        timeout=30,            # seconds per request
    )


# ------------------------------------------------------------------ #
# Repository accessor                                                  #
# ------------------------------------------------------------------ #

def get_repository(access_token: str, repo_full_name: str) -> Repository:
    """
    Return the :class:`~github.Repository.Repository` object for *repo_full_name*.

    Args:
        access_token:   GitHub OAuth / PAT token.  Never logged.
        repo_full_name: Repository in ``"owner/repo"`` format.

    Returns:
        A :class:`~github.Repository.Repository` object.

    Raises:
        :class:`fastapi.HTTPException`:
          - 401 if the token is invalid or revoked.
          - 403 if the token lacks the required scopes or a rate limit is
            active (GitHub returns 403 for abuse-detection rate limits).
          - 404 if the repository does not exist or the token has no read
            permission for it.
          - 429 if the primary API rate limit is exceeded.
          - 502 for all other GitHub API errors.
    """
    _validate_repo_name(repo_full_name)

    try:
        client = get_github_client(access_token)
        repo = client.get_repo(repo_full_name)
        logger.debug(
            "get_repository: fetched repo '%s' (id=%d, default_branch=%s).",
            repo_full_name,
            repo.id,
            repo.default_branch,
        )
        return repo

    except RateLimitExceededException:
        _log_github_error("rate limit exceeded", repo_full_name)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "GitHub API primary rate limit exceeded. "
                "Please retry after the reset time."
            ),
        )

    except GithubException as exc:
        _handle_github_exception(exc, repo_full_name)
        # _handle_github_exception always raises; this line is unreachable
        # but satisfies the type checker.
        raise  # pragma: no cover


# ------------------------------------------------------------------ #
# File content accessor                                                #
# ------------------------------------------------------------------ #

def get_file_content(
    access_token: str,
    repo_full_name: str,
    file_path: str,
    ref: Optional[str] = None,
) -> Optional[str]:
    """
    Fetch the raw text content of a single file from a GitHub repository.

    Args:
        access_token:   GitHub OAuth / PAT token.
        repo_full_name: Repository in ``"owner/repo"`` format.
        file_path:      Relative file path within the repo
                        (e.g. ``"app/services/redis.py"``).
        ref:            Branch name, tag, or commit SHA.  Defaults to the
                        repository's default branch when ``None``.

    Returns:
        The decoded UTF-8 file content as a string, or ``None`` if the file
        does not exist at the given ref or an error occurred.

    Raises:
        :class:`fastapi.HTTPException` for auth / rate-limit errors (these
        are non-recoverable and should propagate to the API caller).
    """
    try:
        repo = get_repository(access_token, repo_full_name)
        kwargs = {"path": file_path}
        if ref:
            kwargs["ref"] = ref

        content_file = repo.get_contents(**kwargs)

        # get_contents returns a list when the path points to a directory.
        if isinstance(content_file, list):
            logger.warning(
                "get_file_content: path '%s' in '%s' is a directory, not a file.",
                file_path,
                repo_full_name,
            )
            return None

        decoded: str = content_file.decoded_content.decode("utf-8", errors="replace")
        logger.debug(
            "get_file_content: fetched '%s' from '%s' (%d bytes).",
            file_path,
            repo_full_name,
            len(decoded),
        )
        return decoded

    except HTTPException:
        # Re-raise auth / rate-limit exceptions from get_repository unchanged.
        raise

    except GithubException as exc:
        if exc.status == 404:
            logger.warning(
                "get_file_content: file '%s' not found in '%s' at ref=%s.",
                file_path,
                repo_full_name,
                ref or "default",
            )
            return None
        _handle_github_exception(exc, repo_full_name, extra=f"file={file_path!r}")
        raise  # pragma: no cover

    except Exception as exc:
        logger.error(
            "get_file_content: unexpected error for '%s' in '%s': %s — %s.",
            file_path,
            repo_full_name,
            type(exc).__name__,
            exc,
        )
        return None


# ------------------------------------------------------------------ #
# Branch helpers                                                       #
# ------------------------------------------------------------------ #

def create_branch(
    access_token: str,
    repo_full_name: str,
    branch_name: str,
    source_branch: Optional[str] = None,
) -> bool:
    """
    Create a new branch in *repo_full_name* branching from *source_branch*.

    Args:
        access_token:   GitHub OAuth / PAT token.
        repo_full_name: Repository in ``"owner/repo"`` format.
        branch_name:    Name for the new branch.
        source_branch:  Branch to branch from; defaults to the repo's default
                        branch when ``None``.

    Returns:
        ``True`` if the branch was created, ``False`` if it already exists
        or an error occurred.

    Raises:
        :class:`fastapi.HTTPException` for auth / rate-limit errors.
    """
    try:
        repo = get_repository(access_token, repo_full_name)
        base = source_branch or repo.default_branch
        base_sha = repo.get_branch(base).commit.sha

        repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=base_sha,
        )
        logger.info(
            "create_branch: created branch '%s' from '%s' in '%s' (sha=%s...).",
            branch_name,
            base,
            repo_full_name,
            base_sha[:7],
        )
        return True

    except HTTPException:
        raise

    except GithubException as exc:
        if exc.status == 422:
            # 422 Unprocessable Entity → branch already exists
            logger.info(
                "create_branch: branch '%s' already exists in '%s'.",
                branch_name,
                repo_full_name,
            )
            return False
        _handle_github_exception(exc, repo_full_name, extra=f"branch={branch_name!r}")
        raise  # pragma: no cover

    except Exception as exc:
        logger.error(
            "create_branch: unexpected error for branch '%s' in '%s': %s — %s.",
            branch_name,
            repo_full_name,
            type(exc).__name__,
            exc,
        )
        return False


# ------------------------------------------------------------------ #
# Validation                                                           #
# ------------------------------------------------------------------ #

def validate_token(access_token: str) -> bool:
    """
    Perform a lightweight check to confirm the token is valid and active.

    Makes a ``GET /user`` call which requires only ``read:user`` scope.
    Does not log the token; logs the username at DEBUG level.

    Args:
        access_token: GitHub OAuth / PAT token to validate.

    Returns:
        ``True`` if the token is valid, ``False`` otherwise.
    """
    try:
        client = get_github_client(access_token)
        user = client.get_user()
        login = user.login
        logger.debug(
            "validate_token: valid token for github_username=%s...",
            login[:4] if len(login) >= 4 else "****",
        )
        return True

    except GithubException as exc:
        if exc.status == 401:
            logger.info("validate_token: token is invalid or expired.")
        else:
            logger.warning(
                "validate_token: GitHub returned status %d.", exc.status
            )
        return False

    except Exception as exc:
        logger.error(
            "validate_token: unexpected error: %s — %s.",
            type(exc).__name__,
            exc,
        )
        return False


# ------------------------------------------------------------------ #
# Internal helpers                                                     #
# ------------------------------------------------------------------ #

def _validate_repo_name(repo_full_name: str) -> None:
    """Raise :class:`HTTPException` (400) if *repo_full_name* is malformed."""
    if not repo_full_name or "/" not in repo_full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"repo_full_name must be in 'owner/repo' format, "
                f"got: {repo_full_name!r}"
            ),
        )
    parts = repo_full_name.split("/")
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid repository name: {repo_full_name!r}",
        )


def _handle_github_exception(
    exc: GithubException,
    repo_full_name: str,
    extra: str = "",
) -> None:
    """
    Map a :class:`~github.GithubException.GithubException` to an
    :class:`~fastapi.HTTPException` and raise it.

    Always raises — never returns.
    """
    context = f"repo='{repo_full_name}'"
    if extra:
        context += f", {extra}"

    if exc.status == 401:
        _log_github_error("token invalid or expired", context)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "GitHub authentication failed. "
                "The access token may have expired or been revoked."
            ),
        )

    if exc.status == 403:
        _log_github_error(f"forbidden (status=403): {exc.data}", context)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "GitHub API access forbidden. "
                "The token may lack required scopes, or a secondary rate limit is active."
            ),
        )

    if exc.status == 404:
        _log_github_error(f"not found (status=404)", context)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Repository '{repo_full_name}' not found or the token has no "
                f"read permission for it."
            ),
        )

    if exc.status == 429:
        _log_github_error("rate limit exceeded (status=429)", context)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="GitHub API rate limit exceeded. Please retry later.",
        )

    # Catch-all for unexpected GitHub API errors (5xx, undocumented 4xx, etc.)
    _log_github_error(f"unexpected status={exc.status}: {exc.data}", context)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"GitHub API error (status {exc.status}). Please retry later.",
    )


def _log_github_error(reason: str, context: str) -> None:
    """Log a GitHub error at ERROR level.  Never includes the access token."""
    logger.error("GitHub API error — %s [%s].", reason, context)
