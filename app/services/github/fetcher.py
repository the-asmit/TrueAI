"""
Fetches repository files from GitHub and returns structured context.

Public interface
────────────────
    fetch_file_context()    → single file fetch with ±window slicing
    fetch_multiple_files()  → batch fetch, skip failures, never abort

All functions are synchronous.  Callers (pipeline nodes) wrap them with
``asyncio.to_thread()`` to avoid blocking the async event loop.

Error handling follows the same contract as ``client.py``:
    - HTTPException is re-raised (auth / rate-limit — non-recoverable).
    - GithubException 404 → return None (file not found).
    - RateLimitExceededException → break batch, return partial results.
    - All other errors → log WARNING, skip, continue.

The raw ``access_token`` is **never** written to any log record.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from fastapi import HTTPException
from github import GithubException, RateLimitExceededException
from github.Repository import Repository

from app.core.logging import get_logger
from app.schemas.github import GitHubFileContext
from app.services.github.client import get_repository

logger = get_logger(__name__)

_DEFAULT_WINDOW: int = 30
_DEFAULT_MAX_FILES: int = 5


# ------------------------------------------------------------------ #
# Public API                                                           #
# ------------------------------------------------------------------ #

def fetch_file_context(
    access_token: str,
    repo_full_name: str,
    file_path: str,
    ref: Optional[str] = None,
    lineno: int = 1,
    window: int = _DEFAULT_WINDOW,
) -> Optional[GitHubFileContext]:
    """
    Fetch a single file from GitHub and return a :class:`GitHubFileContext`.

    When *lineno* and *window* are specified and the file is larger than
    ``2 * window + 1`` lines, returns a focused excerpt centred on *lineno*.
    Otherwise returns the full file content.

    Args:
        access_token:   GitHub OAuth token.  Never logged.
        repo_full_name: Repository in ``"owner/repo"`` format.
        file_path:      Relative path within the repository.
        ref:            Branch, tag, or commit SHA.  ``None`` = default branch.
        lineno:         1-based line number to centre the window on.
        window:         Number of lines above and below *lineno* to include.

    Returns:
        A :class:`GitHubFileContext` with content and metadata, or ``None``
        if the file does not exist or a recoverable error occurred.

    Raises:
        :class:`~fastapi.HTTPException` for auth / rate-limit errors.
    """
    try:
        repo = get_repository(access_token, repo_full_name)
        return _fetch_single_file(repo, file_path, ref, lineno, window)

    except HTTPException:
        raise

    except Exception as exc:
        logger.error(
            "fetch_file_context: unexpected error for '%s' in '%s': %s — %s.",
            file_path, repo_full_name, type(exc).__name__, exc,
        )
        return None


def fetch_multiple_files(
    access_token: str,
    repo_full_name: str,
    file_specs: List[Tuple[str, int]],
    ref: Optional[str] = None,
    window: int = _DEFAULT_WINDOW,
    max_files: int = _DEFAULT_MAX_FILES,
) -> List[GitHubFileContext]:
    """
    Batch-fetch multiple files, deduplicating by path.

    Skips individual file failures silently.  Returns partial results if
    a rate limit is hit mid-batch.  Never aborts the entire batch for a
    single file error.

    Args:
        access_token:   GitHub OAuth token.  Never logged.
        repo_full_name: Repository in ``"owner/repo"`` format.
        file_specs:     List of ``(file_path, lineno)`` tuples.  Innermost
                        (crash-closest) frames should come first.
        ref:            Branch, tag, or commit SHA.  ``None`` = default branch.
        window:         Line window size for each file excerpt.
        max_files:      Maximum number of files to fetch.

    Returns:
        A list of :class:`GitHubFileContext` objects (may be empty).

    Raises:
        :class:`~fastapi.HTTPException` for auth errors during initial
        repository access.
    """
    try:
        repo = get_repository(access_token, repo_full_name)
    except HTTPException:
        raise

    results: List[GitHubFileContext] = []
    seen: set = set()

    for file_path, lineno in file_specs:
        if len(results) >= max_files:
            break

        normalised = file_path.lstrip("/")
        if normalised in seen:
            continue
        seen.add(normalised)

        try:
            ctx = _fetch_single_file(repo, normalised, ref, lineno, window)
            if ctx is not None:
                results.append(ctx)
                logger.debug(
                    "fetch_multiple_files: fetched '%s' (%d chars) | "
                    "batch %d/%d.",
                    normalised, len(ctx.content), len(results), max_files,
                )

        except RateLimitExceededException:
            logger.error(
                "fetch_multiple_files: rate limit hit after %d file(s) — "
                "returning partial results.",
                len(results),
            )
            break

        except GithubException as exc:
            if exc.status in (401, 403):
                logger.error(
                    "fetch_multiple_files: auth/permission error (status=%d) "
                    "— stopping batch.",
                    exc.status,
                )
                break
            logger.warning(
                "fetch_multiple_files: skipping '%s' — GitHub error %d.",
                normalised, exc.status,
            )
            continue

        except Exception as exc:
            logger.warning(
                "fetch_multiple_files: skipping '%s' — %s: %s.",
                normalised, type(exc).__name__, exc,
            )
            continue

    logger.debug(
        "fetch_multiple_files: completed | repo='%s' | requested=%d | "
        "fetched=%d.",
        repo_full_name, len(file_specs), len(results),
    )
    return results


# ------------------------------------------------------------------ #
# Internal helper                                                      #
# ------------------------------------------------------------------ #

def _fetch_single_file(
    repo: Repository,
    file_path: str,
    ref: Optional[str],
    lineno: int,
    window: int,
) -> Optional[GitHubFileContext]:
    """
    Fetch one file from a pre-authenticated :class:`Repository` object.

    Returns a :class:`GitHubFileContext` with optional line windowing,
    or ``None`` if the file is not found or is a directory.

    Raises :class:`~github.GithubException` for non-404 errors so the
    caller can decide whether to skip or abort.
    """
    kwargs: dict = {"path": file_path}
    if ref:
        kwargs["ref"] = ref

    try:
        content_file = repo.get_contents(**kwargs)
    except GithubException as exc:
        if exc.status == 404:
            logger.warning(
                "_fetch_single_file: '%s' not found at ref=%s.",
                file_path, ref or "default",
            )
            return None
        raise

    # get_contents returns a list when the path is a directory.
    if isinstance(content_file, list):
        logger.warning(
            "_fetch_single_file: '%s' is a directory — skipping.",
            file_path,
        )
        return None

    raw_content: str = content_file.decoded_content.decode(
        "utf-8", errors="replace"
    )
    blob_sha: str = content_file.sha
    size_bytes: int = content_file.size

    all_lines = raw_content.splitlines()
    total_lines = len(all_lines)

    # ---- Slice a ±window excerpt when the file is large enough ------- #
    if lineno > 0 and window > 0 and total_lines > (2 * window + 1):
        target_idx = max(0, min(total_lines - 1, lineno - 1))
        start_idx = max(0, target_idx - window)
        end_idx = min(total_lines, target_idx + window + 1)

        sliced = "\n".join(all_lines[start_idx:end_idx])

        return GitHubFileContext(
            file_path=file_path,
            content=sliced,
            start_line=start_idx + 1,
            end_line=end_idx,
            sha=blob_sha,
            ref=ref,
            size_bytes=size_bytes,
            truncated=True,
        )

    # ---- Full file --------------------------------------------------- #
    return GitHubFileContext(
        file_path=file_path,
        content=raw_content,
        start_line=1,
        end_line=total_lines if total_lines > 0 else None,
        sha=blob_sha,
        ref=ref,
        size_bytes=size_bytes,
        truncated=False,
    )
