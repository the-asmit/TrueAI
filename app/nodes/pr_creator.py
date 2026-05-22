"""
PR creator node — applies the validated fix to GitHub and opens a pull request.

Short-circuit:
    If action != "create_pr" → return full state immediately, no I/O.

Flow:
    1. Retrieve the GitHub access token and repo for the user from Supabase.
    2. Parse the fix_diff to extract the list of changed files.
    3. Create a feature branch: trueai/fix-{incident_id[:8]}.
    4. For each changed file:
       a. Fetch the current file content and blob SHA from GitHub.
       b. Apply the unified diff hunk-by-hunk to produce new content.
       c. Commit the updated file to the feature branch.
    5. Create a pull request from the feature branch to the default branch.
    6. Persist the PR record to Supabase.
    7. Write pr_url, pr_number, status = "pr_created" to state.

All synchronous PyGithub / Supabase calls run through asyncio.to_thread()
to avoid blocking the async event loop.

Diff application:
    Uses a pure-Python unified diff applier — no subprocess, no temp files,
    no external tools required.  Handles multiple hunks per file and correctly
    tracks the line offset as hunks are applied in sequence.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.core.logging import get_logger
from app.core.state import IncidentState
from app.services.github.client import get_github_client, create_branch, get_default_branch

logger = get_logger(__name__)

_BRANCH_PREFIX: str = "trueai/fix-"
_FALLBACK_BASE_BRANCH: str = "main"  # used only when credentials are unavailable


async def pr_creator_node(state: IncidentState) -> IncidentState:
    """
    Create a GitHub pull request with the validated code fix.

    Reads:
        action, incident_id, user_id, error_type, root_cause, explanation,
        fix_diff, files_changed

    Writes (success):
        pr_url, pr_number, status = "pr_created"

    Writes (failure):
        error, status = "failed"

    Short-circuits (no I/O) when action != "create_pr".
    """
    state = {**state}
    incident_id: str = state.get("incident_id", "unknown")
    logger.debug("pr_creator_node ENTRY | incident_id=%s", incident_id)

    # ---- Short-circuit: only run when action is "create_pr" ---------- #
    action: str = state.get("action", "")
    if action != "create_pr":
        logger.info(
            "pr_creator_node: action='%s' — skipping PR creation | "
            "incident_id=%s",
            action,
            incident_id,
        )
        return state

    try:
        user_id: str = state.get("user_id", "")
        error_type: str = state.get("error_type", "Unknown Error")
        root_cause: str = state.get("root_cause", "")
        explanation: str = state.get("explanation", "")
        fix_diff: str = state.get("fix_diff", "")
        confidence: float = float(state.get("confidence") or 0.0)

        if not fix_diff.strip():
            state["error"] = "fix_diff is empty — cannot create a PR with no changes."
            state["status"] = "failed"
            logger.error(
                "pr_creator_node: empty fix_diff | incident_id=%s", incident_id
            )
            return state

        # ---- GitHub credentials -------------------------------------- #
        access_token, repo_full_name, base_branch = await _get_github_info(user_id)

        if not access_token or not repo_full_name:
            state["error"] = (
                f"No GitHub credentials found for user_id={user_id!r}."
            )
            state["status"] = "failed"
            logger.error(
                "pr_creator_node: missing credentials | incident_id=%s | "
                "user_id=%s",
                incident_id,
                user_id,
            )
            return state

        # ---- Branch name --------------------------------------------- #
        branch_name: str = f"{_BRANCH_PREFIX}{incident_id[:8]}"

        # ---- Create branch ------------------------------------------- #
        created = await asyncio.to_thread(
            create_branch,
            access_token,
            repo_full_name,
            branch_name,
            base_branch,
        )
        if not created:
            # branch already exists → log and continue (idempotent retry)
            logger.info(
                "pr_creator_node: branch '%s' already exists — proceeding | "
                "incident_id=%s",
                branch_name,
                incident_id,
            )

        # ---- Apply diff file-by-file --------------------------------- #
        files_from_diff = _parse_files_from_diff(fix_diff)
        if not files_from_diff:
            state["error"] = (
                "Could not parse any file paths from fix_diff. "
                "The diff may be malformed."
            )
            state["status"] = "failed"
            logger.error(
                "pr_creator_node: no files parsed from diff | incident_id=%s",
                incident_id,
            )
            return state

        commit_message = (
            f"[TrueAI] Fix: {error_type}\n\n"
            f"Root cause: {root_cause}\n\n"
            f"Auto-generated by TrueAI (incident_id={incident_id})"
        )

        committed_files: List[str] = []
        for file_path in files_from_diff:
            ok = await _commit_file_change(
                access_token=access_token,
                repo_full_name=repo_full_name,
                branch_name=branch_name,
                file_path=file_path,
                fix_diff=fix_diff,
                commit_message=commit_message,
                incident_id=incident_id,
            )
            if ok:
                committed_files.append(file_path)
            else:
                logger.warning(
                    "pr_creator_node: failed to commit '%s' — continuing | "
                    "incident_id=%s",
                    file_path,
                    incident_id,
                )

        if not committed_files:
            state["error"] = (
                "Failed to commit any file changes to the branch. "
                "The diff may not apply cleanly to the current code."
            )
            state["status"] = "failed"
            logger.error(
                "pr_creator_node: no files committed | incident_id=%s | "
                "branch=%s",
                incident_id,
                branch_name,
            )
            return state

        # ---- Create pull request ------------------------------------- #
        pr_title = f"[TrueAI] Fix: {error_type}"
        pr_body = _build_pr_body(
            error_type=error_type,
            root_cause=root_cause,
            explanation=explanation,
            fix_diff=fix_diff,
            incident_id=incident_id,
            confidence=confidence,
        )

        pr_url, pr_number = await _create_pull_request(
            access_token=access_token,
            repo_full_name=repo_full_name,
            branch_name=branch_name,
            base_branch=base_branch,
            title=pr_title,
            body=pr_body,
            incident_id=incident_id,
        )

        if not pr_url or not pr_number:
            state["error"] = "Failed to create GitHub pull request."
            state["status"] = "failed"
            # Update fix status to failed
            try:
                from app.services.supabase import update_fix as _update_fix
                _fix_id = state.get("fix_id")
                if _fix_id:
                    await asyncio.to_thread(_update_fix, str(_fix_id), {"status": "failed"})
            except Exception as _fe:
                logger.warning(
                    "pr_creator_node: could not update fix status=failed | "
                    "incident_id=%s | error=%s", incident_id, _fe
                )
            return state

        # ---- Persist PR record to Supabase -------------------------- #
        await _persist_pr_record(
            state=state,
            pr_url=pr_url,
            pr_number=pr_number,
            branch_name=branch_name,
            repo_full_name=repo_full_name,
            pr_title=pr_title,
            incident_id=incident_id,
        )

        # ---- Write to state ----------------------------------------- #
        state["pr_url"] = pr_url
        state["pr_number"] = pr_number
        state["status"] = "pr_created"

        # Update fix status to applied
        try:
            from app.services.supabase import update_fix as _update_fix
            _fix_id = state.get("fix_id")
            if _fix_id:
                await asyncio.to_thread(_update_fix, str(_fix_id), {"status": "applied"})
        except Exception as _fe:
            logger.warning(
                "pr_creator_node: could not update fix status=applied | "
                "incident_id=%s | error=%s", incident_id, _fe
            )

        logger.info(
            "pr_creator_node EXIT | incident_id=%s | pr_url=%s | pr_number=%d | "
            "files_committed=%d",
            incident_id,
            pr_url,
            pr_number,
            len(committed_files),
        )
        return state

    except Exception as exc:
        state["error"] = (
            f"pr_creator_node unhandled exception: {type(exc).__name__}: {exc}"
        )
        state["status"] = "failed"
        logger.error(
            "pr_creator_node EXCEPTION | incident_id=%s | error=%s",
            incident_id,
            exc,
            exc_info=True,
        )
        # Update fix status to failed
        try:
            from app.services.supabase import update_fix as _update_fix
            _fix_id = state.get("fix_id")
            if _fix_id:
                await asyncio.to_thread(_update_fix, str(_fix_id), {"status": "failed"})
        except Exception as _fe:
            logger.warning(
                "pr_creator_node: could not update fix status=failed (exception path) | "
                "incident_id=%s | error=%s", incident_id, _fe
            )
        return state


# ------------------------------------------------------------------ #
# GitHub credential lookup                                             #
# ------------------------------------------------------------------ #

async def _get_github_info(
    user_id: str,
) -> Tuple[Optional[str], Optional[str], str]:
    """Return (access_token, repo_full_name, base_branch) from Supabase.

    Uses ``get_github_token()`` (which decrypts Fernet ciphertext) for the
    token so that plaintext credentials reach the GitHub API.  Querying the
    raw ``access_token`` column directly would return encrypted bytes and
    cause 401 failures on every GitHub call.

    The base_branch is resolved dynamically via the GitHub API so that repos
    using 'master' or any custom default branch work correctly.
    Falls back to 'main' only when credentials are unavailable or the API
    call fails (handled inside get_default_branch).
    """
    try:
        from app.services.supabase import get_github_token, get_supabase

        # Decrypted token via the service layer (handles Fernet ciphertext).
        access_token: Optional[str] = await asyncio.to_thread(
            get_github_token, user_id
        )

        # Separate query for repo_name (not sensitive, no decryption needed).
        def _query_repo():
            client = get_supabase()
            return (
                client.table("github_tokens")
                .select("repo_name")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

        response = await asyncio.to_thread(_query_repo)
        rows = response.data or []
        repo_full_name: Optional[str] = rows[0].get("repo_name") if rows else None

        # Resolve the actual default branch via the GitHub API.
        # get_default_branch never raises — falls back to 'main' on any error.
        if access_token and repo_full_name:
            base_branch = await get_default_branch(access_token, repo_full_name)
        else:
            base_branch = _FALLBACK_BASE_BRANCH

        return access_token, repo_full_name, base_branch

    except Exception as exc:
        logger.error(
            "pr_creator_node: error fetching GitHub info for user_id=%s: %s",
            user_id,
            exc,
        )
        return None, None, _FALLBACK_BASE_BRANCH



# ------------------------------------------------------------------ #
# Diff parsing                                                         #
# ------------------------------------------------------------------ #

def _parse_files_from_diff(diff: str) -> List[str]:
    """Extract unique target file paths from a unified diff ('+++ b/...' lines)."""
    files: List[str] = []
    seen: set = set()
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            if path and path not in seen:
                seen.add(path)
                files.append(path)
        elif line.startswith("+++ ") and not line.startswith("+++ b/"):
            # Some diffs omit the 'b/' prefix
            path = line[4:].strip()
            if path and path not in seen and path != "/dev/null":
                seen.add(path)
                files.append(path)
    return files


def _extract_file_diff(diff: str, file_path: str) -> str:
    """
    Extract the portion of *diff* that applies to *file_path*.

    Splits on ``--- `` headers to isolate individual file sections.

    Resolution order:
      1. Exact match: ``+++ b/{file_path}`` or ``+++ {file_path}``.
      2. Basename match: ``+++ b/{basename}`` or ``+++ {basename}``.
         Handles the case where the diff was generated against the original
         unresolved path (e.g. ``main.py``) but the file was committed to a
         resolved path (e.g. ``backend/main.py``) via repo tree search.
    """
    sections = re.split(r"(?=^--- )", diff, flags=re.MULTILINE)

    # Pass 1: exact path match
    for section in sections:
        if f"+++ b/{file_path}" in section or f"+++ {file_path}" in section:
            return section

    # Pass 2: basename match
    basename = Path(file_path).name
    for section in sections:
        if f"+++ b/{basename}" in section or f"+++ {basename}" in section:
            return section

    return ""


def _apply_unified_diff(original: str, file_diff: str) -> str:
    """
    Apply a unified diff to *original* file content and return the result.

    Processes hunks in order, tracking a line offset so that each subsequent
    hunk is applied at the correct position after earlier hunks have shifted
    the line count up or down.

    If a hunk cannot be applied (index out of range), it is skipped with a
    warning log — a partial application is better than a crash.
    """
    lines: List[str] = original.splitlines()
    offset: int = 0

    hunk_pattern = re.compile(
        r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n(.*?)(?=^@@|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    for hunk_match in hunk_pattern.finditer(file_diff):
        old_start = int(hunk_match.group(1)) - 1   # 0-indexed
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
                "out of range (file has %d lines) — skipping hunk",
                old_start + 1,
                adjusted_start,
                len(lines),
            )
            continue

        lines[adjusted_start:end_idx] = new_lines
        offset += len(new_lines) - len(old_lines)

    return "\n".join(lines)


# ------------------------------------------------------------------ #
# File commit                                                          #
# ------------------------------------------------------------------ #

async def _commit_file_change(
    access_token: str,
    repo_full_name: str,
    branch_name: str,
    file_path: str,
    fix_diff: str,
    commit_message: str,
    incident_id: str,
) -> bool:
    """
    Fetch the current file, apply the diff, and commit the result.

    Returns True on success, False on any error.
    """
    try:
        from app.services.github.client import get_repository

        def _get_contents():
            from github import GithubException
            repo = get_repository(access_token, repo_full_name)
            try:
                contents = repo.get_contents(file_path, ref=branch_name)
                return repo, contents, file_path
            except GithubException as e:
                if e.status == 404:
                    # Try to find the file by searching the repo tree
                    try:
                        tree = repo.get_git_tree(sha="HEAD", recursive=True)
                        filename = file_path.replace("\\", "/").split("/")[-1]
                        matches = [
                            el.path for el in tree.tree
                            if el.type == "blob" and el.path.endswith(filename)
                        ]
                        if len(matches) == 1:
                            resolved_path = matches[0]
                        elif len(matches) > 1:
                            # Score by right-to-left path-part overlap
                            orig_parts = file_path.replace("\\", "/").split("/")
                            def score(p):
                                cand_parts = p.split("/")
                                overlap = sum(
                                    1 for a, b in zip(
                                        reversed(orig_parts), reversed(cand_parts)
                                    ) if a == b
                                )
                                return (overlap, -len(cand_parts))
                            resolved_path = max(matches, key=score)
                        else:
                            raise  # no match found, re-raise original 404
                        contents = repo.get_contents(resolved_path, ref=branch_name)
                        return repo, contents, resolved_path
                    except Exception:
                        raise e
                raise

        repo, contents, file_path = await asyncio.to_thread(_get_contents)

        # Handle directory case (get_contents returns list for dirs)
        if isinstance(contents, list):
            logger.warning(
                "pr_creator_node: '%s' is a directory, not a file | "
                "incident_id=%s",
                file_path,
                incident_id,
            )
            return False

        original_content: str = contents.decoded_content.decode(
            "utf-8", errors="replace"
        )
        current_sha: str = contents.sha

        # Extract and apply just this file's portion of the diff
        file_diff_section = _extract_file_diff(fix_diff, file_path)
        if not file_diff_section:
            logger.warning(
                "pr_creator_node: no diff section found for '%s' | "
                "incident_id=%s",
                file_path,
                incident_id,
            )
            return False

        new_content = _apply_unified_diff(original_content, file_diff_section)

        if new_content == original_content:
            logger.warning(
                "pr_creator_node: diff produced no change in '%s' — "
                "patch may not apply cleanly | incident_id=%s",
                file_path,
                incident_id,
            )
            return False

        def _update():
            repo.update_file(
                path=file_path,
                message=commit_message,
                content=new_content,
                sha=current_sha,
                branch=branch_name,
            )

        await asyncio.to_thread(_update)
        logger.debug(
            "pr_creator_node: committed '%s' to branch '%s' | incident_id=%s",
            file_path,
            branch_name,
            incident_id,
        )
        return True

    except HTTPException as http_exc:
        logger.error(
            "pr_creator_node: GitHub API error %d committing '%s' | "
            "incident_id=%s | detail=%s",
            http_exc.status_code,
            file_path,
            incident_id,
            http_exc.detail,
        )
        return False
    except Exception as exc:
        logger.error(
            "pr_creator_node: failed to commit '%s' | incident_id=%s | "
            "error=%s — %s",
            file_path,
            incident_id,
            type(exc).__name__,
            exc,
        )
        return False


# ------------------------------------------------------------------ #
# Pull request creation                                                #
# ------------------------------------------------------------------ #

async def _create_pull_request(
    access_token: str,
    repo_full_name: str,
    branch_name: str,
    base_branch: str,
    title: str,
    body: str,
    incident_id: str,
) -> Tuple[Optional[str], Optional[int]]:
    """
    Open a GitHub pull request and return (pr_url, pr_number).
    Returns (None, None) on failure.
    """
    try:
        from app.services.github.client import get_repository

        def _create():
            repo = get_repository(access_token, repo_full_name)
            pr = repo.create_pull(
                title=title,
                body=body,
                head=branch_name,
                base=base_branch,
                draft=False,
            )
            return pr.html_url, pr.number

        pr_url, pr_number = await asyncio.to_thread(_create)
        logger.info(
            "pr_creator_node: PR created | incident_id=%s | pr_number=%d | "
            "pr_url=%s",
            incident_id,
            pr_number,
            pr_url,
        )
        return pr_url, pr_number

    except HTTPException as http_exc:
        logger.error(
            "pr_creator_node: GitHub API error %d creating PR | "
            "incident_id=%s | detail=%s",
            http_exc.status_code,
            incident_id,
            http_exc.detail,
        )
        return None, None
    except Exception as exc:
        logger.error(
            "pr_creator_node: failed to create PR | incident_id=%s | "
            "error=%s — %s",
            incident_id,
            type(exc).__name__,
            exc,
        )
        return None, None


# ------------------------------------------------------------------ #
# Supabase persistence                                                 #
# ------------------------------------------------------------------ #

async def _persist_pr_record(
    state: Dict[str, Any],
    pr_url: str,
    pr_number: int,
    branch_name: str,
    repo_full_name: str,
    pr_title: str,
    incident_id: str,
) -> None:
    """
    Write the PR record to Supabase.  Logs errors but never raises —
    a persistence failure should not undo the successfully created PR.
    """
    try:
        from app.services.supabase import create_pull_request as supabase_create_pr

        fix_id = state.get("fix_id")   # set by validator_node after fix persisted

        pr_data: Dict[str, Any] = {
            "fix_id": str(fix_id) if fix_id else None,
            "pr_url": pr_url,
            "pr_number": pr_number,
            "branch_name": branch_name,
            "status": "open",
        }

        await asyncio.to_thread(supabase_create_pr, pr_data)
        logger.debug(
            "pr_creator_node: PR record saved to Supabase | incident_id=%s",
            incident_id,
        )
    except Exception as exc:
        logger.error(
            "pr_creator_node: failed to persist PR record to Supabase | "
            "incident_id=%s | error=%s — %s",
            incident_id,
            type(exc).__name__,
            exc,
        )


# ------------------------------------------------------------------ #
# PR body builder                                                      #
# ------------------------------------------------------------------ #

def _build_pr_body(
    error_type: str,
    root_cause: str,
    explanation: str,
    fix_diff: str,
    incident_id: str,
    confidence: float,
) -> str:
    """Build a structured Markdown PR description."""
    diff_preview = fix_diff[:3000] + "\n... (truncated)" if len(fix_diff) > 3000 else fix_diff
    return f"""## 🤖 TrueAI Automated Fix

> **Incident ID:** `{incident_id}`
> **Error Type:** `{error_type}`
> **Confidence:** `{confidence:.0%}`

---

### Root Cause

{root_cause}

---

### Explanation

{explanation}

---

### Changes

```diff
{diff_preview}
```

---

*This pull request was created automatically by [TrueAI](https://github.com/trueai).
Review the changes carefully before merging.  Confidence score above reflects
the AI's certainty about the root cause — always apply human judgement.*"""
