"""
Pull request creation and file commit service for TrueAI.

Public interface
────────────────
    apply_diff_and_commit()  → fetch file, apply unified diff, commit to branch
    create_pull_request()    → open a GitHub PR, return (pr_url, pr_number)

All functions are synchronous.  Callers (pipeline nodes) wrap them with
``asyncio.to_thread()`` to avoid blocking the async event loop.

Diff application
────────────────
Uses a pure-Python unified diff applier — no subprocess, no temp files, no
external tools required.  The hunk parsing logic mirrors the implementation
already present in ``app/nodes/pr_creator.py`` so the two stay behaviorally
consistent.  Multiple hunks per file are handled in sequence; a line offset
is tracked to account for earlier hunks shifting the line count.

Error handling contract
───────────────────────
    HTTPException is re-raised (auth / rate-limit — non-recoverable).
    GithubException 422 on PR creation → PR already exists for that branch,
        find and return the existing PR instead of raising.
    All other GithubException → mapped to HTTPException by client.py helpers.
    Unexpected exceptions → logged at ERROR, caller receives (None, None) or
        False depending on return type.

The raw ``access_token`` is **never** written to any log record.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from fastapi import HTTPException
from github import GithubException, RateLimitExceededException

from app.core.logging import get_logger
from app.schemas.github import GitHubPRRequest
from app.services.github.client import get_repository

logger = get_logger(__name__)


# ------------------------------------------------------------------ #
# Public: apply diff and commit                                        #
# ------------------------------------------------------------------ #

def apply_diff_and_commit(
    access_token: str,
    repo_full_name: str,
    branch_name: str,
    file_path: str,
    fix_diff: str,
    commit_message: str,
) -> bool:
    """
    Fetch the current content of *file_path*, apply the unified diff that
    concerns it, and commit the result to *branch_name*.

    The function handles the case where the file does not yet exist on the
    branch (falls back to the repository's default branch) so that a freshly
    created feature branch does not block the commit.

    Args:
        access_token:    GitHub OAuth token.  Never logged.
        repo_full_name:  Repository in ``"owner/repo"`` format.
        branch_name:     Target branch for the commit.
        file_path:       Relative path of the file to update.
        fix_diff:        Full unified diff produced by the fix generator.
                         May contain hunks for multiple files; only the
                         section relevant to *file_path* is applied.
        commit_message:  Git commit message.

    Returns:
        ``True`` on success, ``False`` on any recoverable error.

    Raises:
        :class:`~fastapi.HTTPException` for auth / rate-limit errors.
    """
    try:
        repo = get_repository(access_token, repo_full_name)

        # ---- Fetch current file content and blob SHA ----------------- #
        try:
            content_file = repo.get_contents(file_path, ref=branch_name)
        except GithubException as exc:
            if exc.status == 404:
                # File not yet on branch — fetch from default branch.
                logger.debug(
                    "apply_diff_and_commit: '%s' not on branch '%s' — "
                    "fetching from default branch.",
                    file_path, branch_name,
                )
                try:
                    content_file = repo.get_contents(file_path)
                except GithubException as inner_exc:
                    if inner_exc.status == 404:
                        logger.warning(
                            "apply_diff_and_commit: '%s' not found in '%s' "
                            "on any branch — skipping.",
                            file_path, repo_full_name,
                        )
                        return False
                    raise
            else:
                raise

        # get_contents returns a list when path is a directory.
        if isinstance(content_file, list):
            logger.warning(
                "apply_diff_and_commit: '%s' is a directory — skipping.",
                file_path,
            )
            return False

        original_content: str = content_file.decoded_content.decode(
            "utf-8", errors="replace"
        )
        current_sha: str = content_file.sha

        # ---- Extract and apply the file-specific portion of the diff - #
        file_diff_section = _extract_file_diff(fix_diff, file_path)
        if not file_diff_section:
            logger.warning(
                "apply_diff_and_commit: no diff section found for '%s' — "
                "patch may not reference this file.",
                file_path,
            )
            return False

        new_content = _apply_unified_diff(original_content, file_diff_section)

        if new_content == original_content:
            logger.warning(
                "apply_diff_and_commit: diff produced no change in '%s' — "
                "patch may not apply cleanly to current content.",
                file_path,
            )
            return False

        # ---- Commit the updated content ------------------------------ #
        repo.update_file(
            path=file_path,
            message=commit_message,
            content=new_content,
            sha=current_sha,
            branch=branch_name,
        )

        logger.debug(
            "apply_diff_and_commit: committed '%s' to branch '%s' in '%s'.",
            file_path, branch_name, repo_full_name,
        )
        return True

    except HTTPException:
        raise

    except RateLimitExceededException:
        logger.error(
            "apply_diff_and_commit: GitHub rate limit exceeded committing "
            "'%s' to '%s'.",
            file_path, repo_full_name,
        )
        raise HTTPException(
            status_code=429,
            detail="GitHub API rate limit exceeded. Please retry later.",
        )

    except GithubException as exc:
        logger.error(
            "apply_diff_and_commit: GitHub error %d committing '%s' to '%s': %s.",
            exc.status, file_path, repo_full_name, exc.data,
        )
        return False

    except Exception as exc:
        logger.error(
            "apply_diff_and_commit: unexpected error committing '%s' to '%s': "
            "%s — %s.",
            file_path, repo_full_name, type(exc).__name__, exc,
        )
        return False


# ------------------------------------------------------------------ #
# Public: create pull request                                          #
# ------------------------------------------------------------------ #

def create_pull_request(
    access_token: str,
    repo_full_name: str,
    request: GitHubPRRequest,
) -> Tuple[Optional[str], Optional[int]]:
    """
    Create a GitHub pull request from *request.branch_name* into
    *request.base_branch* and return ``(pr_url, pr_number)``.

    If a PR already exists for the same head branch (GitHub returns 422),
    the existing PR is located and its URL and number are returned — making
    this call idempotent.

    Args:
        access_token:    GitHub OAuth token.  Never logged.
        repo_full_name:  Repository in ``"owner/repo"`` format.
        request:         Validated :class:`~app.schemas.github.GitHubPRRequest`
                         containing title, body, branch names, labels, etc.

    Returns:
        ``(pr_url, pr_number)`` on success or if PR already exists.
        ``(None, None)`` on any non-idempotent failure.

    Raises:
        :class:`~fastapi.HTTPException` for auth / rate-limit errors.
    """
    try:
        repo = get_repository(access_token, repo_full_name)

        # ---- Attempt to create the PR -------------------------------- #
        try:
            pr = repo.create_pull(
                title=request.title,
                body=request.body,
                head=request.branch_name,
                base=request.base_branch,
                draft=request.draft,
            )
        except GithubException as exc:
            if exc.status == 422:
                # PR already exists for this branch — find and return it.
                logger.info(
                    "create_pull_request: PR for branch '%s' already exists "
                    "in '%s' — fetching existing PR.",
                    request.branch_name, repo_full_name,
                )
                existing = _find_existing_pr(repo, request.branch_name)
                if existing:
                    return existing
                logger.error(
                    "create_pull_request: 422 from GitHub but could not find "
                    "existing PR for branch '%s' in '%s'.",
                    request.branch_name, repo_full_name,
                )
                return None, None
            raise

        # ---- Apply labels -------------------------------------------- #
        if request.labels:
            _apply_labels(repo, pr, request.labels, repo_full_name)

        # ---- Apply assignees ----------------------------------------- #
        if request.assignees:
            try:
                pr.add_to_assignees(*request.assignees)
                logger.debug(
                    "create_pull_request: PR #%d assignees set to %s.",
                    pr.number, request.assignees,
                )
            except GithubException as exc:
                # Non-fatal — assignees are a best-effort decoration.
                logger.warning(
                    "create_pull_request: could not set assignees on PR #%d: "
                    "%d — %s.",
                    pr.number, exc.status, exc.data,
                )

        logger.info(
            "create_pull_request: PR #%d created in '%s' | url=%s.",
            pr.number, repo_full_name, pr.html_url,
        )
        return pr.html_url, pr.number

    except HTTPException:
        raise

    except RateLimitExceededException:
        logger.error(
            "create_pull_request: GitHub rate limit exceeded for '%s'.",
            repo_full_name,
        )
        raise HTTPException(
            status_code=429,
            detail="GitHub API rate limit exceeded. Please retry later.",
        )

    except GithubException as exc:
        logger.error(
            "create_pull_request: GitHub error %d for '%s': %s.",
            exc.status, repo_full_name, exc.data,
        )
        return None, None

    except Exception as exc:
        logger.error(
            "create_pull_request: unexpected error for '%s': %s — %s.",
            repo_full_name, type(exc).__name__, exc,
        )
        return None, None


# ------------------------------------------------------------------ #
# Internal: PR helpers                                                 #
# ------------------------------------------------------------------ #

def _find_existing_pr(
    repo,
    branch_name: str,
) -> Tuple[Optional[str], Optional[int]]:
    """
    Search open pull requests to find one whose head matches *branch_name*.

    Returns ``(pr_url, pr_number)`` or ``(None, None)`` if no match found.
    """
    try:
        for pr in repo.get_pulls(state="open"):
            if pr.head.ref == branch_name:
                logger.debug(
                    "_find_existing_pr: found PR #%d for branch '%s'.",
                    pr.number, branch_name,
                )
                return pr.html_url, pr.number
    except Exception as exc:
        logger.warning(
            "_find_existing_pr: error searching PRs for branch '%s': %s.",
            branch_name, exc,
        )
    return None, None


def _apply_labels(repo, pr, labels: List[str], repo_full_name: str) -> None:
    """
    Apply *labels* to *pr*, creating any that do not yet exist in the repo.

    Non-fatal — label failures are logged and skipped.
    """
    existing_names = {lbl.name for lbl in repo.get_labels()}

    for label_name in labels:
        try:
            if label_name not in existing_names:
                repo.create_label(name=label_name, color="0075ca")
                logger.debug(
                    "_apply_labels: created label '%s' in '%s'.",
                    label_name, repo_full_name,
                )
        except GithubException as exc:
            # 422 = label already exists (race condition) — safe to ignore.
            if exc.status != 422:
                logger.warning(
                    "_apply_labels: could not create label '%s': %d — %s.",
                    label_name, exc.status, exc.data,
                )

    try:
        pr.add_to_labels(*labels)
        logger.debug(
            "_apply_labels: labels %s applied to PR #%d.",
            labels, pr.number,
        )
    except GithubException as exc:
        logger.warning(
            "_apply_labels: could not apply labels to PR #%d: %d — %s.",
            pr.number, exc.status, exc.data,
        )


# ------------------------------------------------------------------ #
# Internal: unified diff applier                                       #
# ------------------------------------------------------------------ #
# Logic mirrors app/nodes/pr_creator.py — kept here as the canonical
# service-layer implementation.  pr_creator_node is left unchanged.

def _extract_file_diff(diff: str, file_path: str) -> str:
    """
    Extract the portion of *diff* that applies to *file_path*.

    Splits on ``--- `` headers to isolate individual file sections and
    returns the first section whose ``+++ `` line references *file_path*.
    """
    sections = re.split(r"(?=^--- )", diff, flags=re.MULTILINE)
    for section in sections:
        if f"+++ b/{file_path}" in section or f"+++ {file_path}" in section:
            return section
    return ""


def _apply_unified_diff(original: str, file_diff: str) -> str:
    """
    Apply a unified diff to *original* file content and return the result.

    Processes hunks in order, tracking a line offset so that each subsequent
    hunk is applied at the correct position after earlier hunks have shifted
    the line count up or down.

    If a hunk cannot be applied (index out of range), it is skipped with a
    WARNING log — a partial application is better than a crash.
    """
    lines: List[str] = original.splitlines()
    offset: int = 0

    hunk_pattern = re.compile(
        r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n(.*?)(?=^@@|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    for hunk_match in hunk_pattern.finditer(file_diff):
        old_start = int(hunk_match.group(1)) - 1   # convert to 0-indexed
        old_count_str = hunk_match.group(2)
        old_count = int(old_count_str) if old_count_str else 1
        hunk_body = hunk_match.group(5)

        old_lines: List[str] = []
        new_lines: List[str] = []

        for diff_line in hunk_body.splitlines():
            if diff_line.startswith("-"):
                old_lines.append(diff_line[1:])
            elif diff_line.startswith("+"):
                new_lines.append(diff_line[1:])
            elif diff_line.startswith(" "):
                old_lines.append(diff_line[1:])
                new_lines.append(diff_line[1:])
            elif diff_line.startswith("\\"):
                pass  # "\ No newline at end of file" — skip

        adjusted_start = old_start + offset
        end_idx = adjusted_start + len(old_lines)

        if adjusted_start < 0 or end_idx > len(lines) + 1:
            logger.warning(
                "_apply_unified_diff: hunk at old_start=%d (adjusted=%d) is "
                "out of range (file has %d lines) — skipping hunk.",
                old_start + 1, adjusted_start, len(lines),
            )
            continue

        lines[adjusted_start:end_idx] = new_lines
        offset += len(new_lines) - len(old_lines)

    return "\n".join(lines)
