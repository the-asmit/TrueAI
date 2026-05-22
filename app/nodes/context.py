"""
Context enrichment node — fetches relevant source files from GitHub.

Strategy:
    - Reverse the stack frames (last = closest to crash = highest priority).
    - Deduplicate by filename.
    - Fetch up to MAX_FILES (5) files.
    - For each file, slice a ±CONTEXT_WINDOW (30) line window around the
      error line so the LLM receives focused context, not entire files.
    - Handle each frame independently: file not found, rate limit, wrong
      path → log WARNING/ERROR, skip, continue.  A single frame failure
      never aborts the enrichment pass.
    - If EVERY frame fails → set error, status = "failed", return full state.

All GitHub / Supabase calls are run via asyncio.to_thread() because the
underlying libraries (PyGithub, supabase-py) are synchronous.  Running them
directly in an async function would block the event loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.core.logging import get_logger
from app.core.state import IncidentState
from app.services.github.client import get_file_content

logger = get_logger(__name__)

MAX_FILES: int = 5
CONTEXT_WINDOW: int = 30   # lines above and below the error line


async def context_node(state: IncidentState) -> IncidentState:
    """
    Fetch GitHub source files for each user-code stack frame.

    Reads:
        user_id, stack_frames

    Writes:
        github_context  →  Dict[filename, content_window]
        status = "failed" + error  if ALL frames fail

    On partial failure (some frames succeed, some fail): continues with
    whatever was fetched — never sets status="failed" for a partial result.
    """
    state = {**state}
    incident_id = state.get("incident_id", "unknown")
    user_id: str = state.get("user_id", "")
    stack_frames: List[Dict[str, Any]] = state.get("stack_frames") or []
    logger.debug(
        "context_node ENTRY | incident_id=%s | frame_count=%d",
        incident_id,
        len(stack_frames),
    )

    try:
        if not stack_frames:
            logger.warning(
                "context_node: no stack_frames in state — skipping GitHub fetch | "
                "incident_id=%s",
                incident_id,
            )
            state["github_context"] = {}
            return state

        # ---- Fetch GitHub credentials -------------------------------- #
        access_token, repo_full_name = await _get_github_credentials(user_id)

        if not access_token or not repo_full_name:
            state["error"] = (
                f"No GitHub token or repository configured for user_id={user_id!r}. "
                "Connect a GitHub account and set a default repository."
            )
            state["status"] = "failed"
            logger.error(
                "context_node: missing GitHub credentials | "
                "incident_id=%s | user_id=%s | has_token=%s | has_repo=%s",
                incident_id,
                user_id,
                bool(access_token),
                bool(repo_full_name),
            )
            return state

        # ---- Build prioritised file list ----------------------------- #
        # Reverse so that the innermost (crash-closest) frames are first.
        files_to_fetch: List[Tuple[str, int]] = _prioritise_frames(stack_frames)

        # ---- Fetch each file independently --------------------------- #
        github_context: Dict[str, str] = {}
        fetch_errors: int = 0

        for file_path, lineno in files_to_fetch:
            if len(github_context) >= MAX_FILES:
                break

            content = await _fetch_file_window(
                access_token=access_token,
                repo_full_name=repo_full_name,
                file_path=file_path,
                lineno=lineno,
                incident_id=incident_id,
            )

            if content is not None:
                github_context[file_path] = content
            else:
                fetch_errors += 1

        # ---- Evaluate result ---------------------------------------- #
        if not github_context and fetch_errors > 0:
            logger.warning(
                "context_node: ALL file fetches failed | incident_id=%s | "
                "repo=%s | attempted=%d — continuing with empty context",
                incident_id,
                repo_full_name,
                fetch_errors,
            )
            state["github_context"] = {}
            return state

        state["github_context"] = github_context

        logger.debug(
            "context_node EXIT | incident_id=%s | files_fetched=%d | "
            "files_failed=%d",
            incident_id,
            len(github_context),
            fetch_errors,
        )
        return state

    except Exception as exc:
        state["error"] = (
            f"context_node unhandled exception: {type(exc).__name__}: {exc}"
        )
        state["status"] = "failed"
        logger.error(
            "context_node EXCEPTION | incident_id=%s | error=%s",
            incident_id,
            exc,
            exc_info=True,
        )
        return state


# ------------------------------------------------------------------ #
# GitHub credential lookup                                             #
# ------------------------------------------------------------------ #

async def _get_github_credentials(
    user_id: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (access_token, repo_full_name) for *user_id* from Supabase.

    Uses ``get_github_token()`` (which decrypts Fernet ciphertext) for the
    token, and a separate Supabase query for the repo_name.  Querying the
    raw ``access_token`` column directly would return the encrypted bytes
    and cause GitHub API calls to fail with 401.
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
            response = (
                client.table("github_tokens")
                .select("repo_name")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = response.data or []
            return rows[0].get("repo_name") if rows else None

        repo_full_name: Optional[str] = await asyncio.to_thread(_query_repo)

        return access_token, repo_full_name

    except Exception as exc:
        logger.error(
            "context_node: failed to fetch GitHub credentials for "
            "user_id=%s: %s — %s",
            user_id,
            type(exc).__name__,
            exc,
        )
        return None, None



# ------------------------------------------------------------------ #
# Frame prioritisation                                                 #
# ------------------------------------------------------------------ #

def _prioritise_frames(
    stack_frames: List[Dict[str, Any]],
) -> List[Tuple[str, int]]:
    """
    Return up to MAX_FILES (file_path, lineno) tuples, deduplicated,
    with crash-closest frames (last in the list) first.
    """
    seen: set = set()
    result: List[Tuple[str, int]] = []

    for frame in reversed(stack_frames):
        file_path: Optional[str] = frame.get("filename")
        lineno: int = int(frame.get("lineno") or 1)

        if not file_path:
            continue

        # Normalise path (strip leading /)
        file_path = file_path.lstrip("/")

        if file_path in seen:
            continue  # already queued
        seen.add(file_path)
        result.append((file_path, lineno))

        if len(result) >= MAX_FILES:
            break

    return result


# ------------------------------------------------------------------ #
# File fetch with windowing                                            #
# ------------------------------------------------------------------ #

async def _fetch_file_window(
    access_token: str,
    repo_full_name: str,
    file_path: str,
    lineno: int,
    incident_id: str,
) -> Optional[str]:
    """
    Fetch *file_path* from GitHub and return a ±CONTEXT_WINDOW slice around
    *lineno*.  Returns None on any error (caller decides whether to skip or
    fail the pipeline).

    Error handling:
        HTTPException(404) → file not found → WARNING
        HTTPException(429) → rate limit → ERROR
        HTTPException(403) → permission / rate limit → ERROR
        HTTPException(401) → bad token → ERROR
        Any other exception → ERROR
    """
    try:
        raw_content: Optional[str] = await asyncio.to_thread(
            get_file_content,
            access_token,
            repo_full_name,
            file_path,
        )

        if raw_content is None:
            # ---- Fallback: search the repo tree for the file ---------- #
            resolved_path = await _find_file_in_repo(
                access_token, repo_full_name, file_path
            )
            if resolved_path and resolved_path != file_path:
                logger.info(
                    "context_node: resolved '%s' → '%s' via repo tree search | "
                    "incident_id=%s",
                    file_path,
                    resolved_path,
                    incident_id,
                )
                raw_content = await asyncio.to_thread(
                    get_file_content,
                    access_token,
                    repo_full_name,
                    resolved_path,
                )

            if raw_content is None:
                logger.warning(
                    "context_node: get_file_content returned None for '%s' in '%s' "
                    "(including fallback tree search) | incident_id=%s",
                    file_path,
                    repo_full_name,
                    incident_id,
                )
                return None

        windowed = _extract_window(raw_content, lineno)
        logger.debug(
            "context_node: fetched '%s' (%d chars, window around line %d) | "
            "incident_id=%s",
            file_path,
            len(windowed),
            lineno,
            incident_id,
        )
        return windowed

    except HTTPException as http_exc:
        if http_exc.status_code == 404:
            logger.warning(
                "context_node: file '%s' not found in '%s' (404) — skipping | "
                "incident_id=%s",
                file_path,
                repo_full_name,
                incident_id,
            )
        elif http_exc.status_code == 429:
            logger.error(
                "context_node: GitHub rate limit hit fetching '%s' from '%s' "
                "(429) — skipping | incident_id=%s",
                file_path,
                repo_full_name,
                incident_id,
            )
        elif http_exc.status_code == 401:
            logger.error(
                "context_node: GitHub token invalid or expired fetching '%s' "
                "from '%s' (401) — skipping | incident_id=%s",
                file_path,
                repo_full_name,
                incident_id,
            )
        else:
            logger.error(
                "context_node: GitHub API error %d fetching '%s' from '%s' — "
                "skipping | incident_id=%s | detail=%s",
                http_exc.status_code,
                file_path,
                repo_full_name,
                incident_id,
                http_exc.detail,
            )
        return None

    except Exception as exc:
        logger.error(
            "context_node: unexpected error fetching '%s' from '%s' — "
            "skipping | incident_id=%s | error=%s — %s",
            file_path,
            repo_full_name,
            incident_id,
            type(exc).__name__,
            exc,
        )
        return None


# ------------------------------------------------------------------ #
# Repo tree path resolution                                            #
# ------------------------------------------------------------------ #

async def _find_file_in_repo(
    access_token: str,
    repo_full_name: str,
    file_path: str,
) -> Optional[str]:
    """
    Search the repository's full git tree for a file that matches the
    basename of *file_path*, returning the best-matching full path.

    Resolution algorithm:
      1. Fetch the recursive git tree via ``repo.get_git_tree(sha="HEAD",
         recursive=True)``.
      2. Extract the basename from *file_path* (e.g. ``main.py`` from
         ``backend/app/main.py``).
      3. Collect every blob whose path ends with that basename.
      4. Zero matches  → return None.
      5. One match     → return that path directly.
      6. Many matches  → score each candidate by counting right-to-left
         path-part overlaps with the original *file_path*, then return the
         highest-scoring candidate (shorter path wins on ties).

    Args:
        access_token:   Decrypted GitHub OAuth token.
        repo_full_name: ``owner/repo`` string.
        file_path:      The path that failed to resolve directly.

    Returns:
        A resolved repository-relative path string, or None if no match
        is found or an error occurs.
    """
    def _search_tree() -> Optional[str]:
        from app.services.github.client import get_github_client, get_repository
        from github import GithubException

        try:
            client = get_github_client(access_token)
            repo = get_repository(client, repo_full_name)

            # Fetch the full recursive tree (expensive but cached by GitHub)
            tree = repo.get_git_tree(sha="HEAD", recursive=True)

            filename = Path(file_path).name  # e.g. "main.py"

            # Collect all blobs whose path ends with the target filename
            candidates = [
                element.path
                for element in tree.tree
                if element.type == "blob"
                and element.path.endswith(filename)
            ]

            if not candidates:
                return None

            if len(candidates) == 1:
                return candidates[0]

            # Score candidates by right-to-left path-part overlap
            original_parts = Path(file_path).parts

            def _overlap_score(candidate: str) -> tuple:
                candidate_parts = Path(candidate).parts
                # Count matching parts from the right
                score = 0
                for orig, cand in zip(
                    reversed(original_parts), reversed(candidate_parts)
                ):
                    if orig == cand:
                        score += 1
                    else:
                        break
                # Negate length so shorter paths win on equal score (min depth)
                return (score, -len(candidate_parts))

            return max(candidates, key=_overlap_score)

        except GithubException as exc:
            logger.warning(
                "context_node: git tree fetch failed for '%s' in '%s': %s — %s",
                file_path,
                repo_full_name,
                type(exc).__name__,
                exc,
            )
            return None
        except Exception as exc:
            logger.warning(
                "context_node: unexpected error in _find_file_in_repo for '%s': "
                "%s — %s",
                file_path,
                type(exc).__name__,
                exc,
            )
            return None

    return await asyncio.to_thread(_search_tree)


# ------------------------------------------------------------------ #
# Line windowing                                                       #
# ------------------------------------------------------------------ #

def _extract_window(content: str, lineno: int) -> str:
    """
    Return a slice of *content* centred on *lineno* (1-based) with
    CONTEXT_WINDOW lines above and below, annotated with line numbers.

    Annotating with line numbers is critical so that the LLM and the diff
    applier can reference exact positions without misalignment.
    """
    all_lines = content.splitlines()
    total = len(all_lines)

    # Convert to 0-indexed, clamp
    target_idx = max(0, min(total - 1, lineno - 1))
    start_idx = max(0, target_idx - CONTEXT_WINDOW)
    end_idx = min(total, target_idx + CONTEXT_WINDOW + 1)

    window_lines = []
    for i in range(start_idx, end_idx):
        # Prefix: line number right-aligned + marker for the error line
        prefix = f"{i + 1:4d} {'→' if i == target_idx else ' '} "
        window_lines.append(prefix + all_lines[i])

    return "\n".join(window_lines)
