"""
Context node — gathers the source code the agents reason about (a tool, not an agent).

Reads:
    user_id, event, pending_file_requests, repo, source_files, code_context

Writes:
    repo, repo_note, can_push, source_files, code_context, pending_file_requests
    (GitHub outage) status = "failed", error, error_retryable

First call:
    1. Pick the repository for this incident: the mapping for its Sentry
       project, else the user's default repository.
    2. Pin the target branch to a commit SHA (every later read and the PR
       itself use this exact commit).
    3. Map in-app stack frames to repository files (innermost first) and read
       them, keeping full contents for editing and numbered excerpts for
       prompts: the file header (imports) plus a window around each frame line.

Follow-up calls (the Investigator asked for more files):
    Resolve and read only the requested paths.

No repository / no GitHub connection is not fatal — the analysis continues
on Sentry data alone and the incident is flagged instead of getting a PR.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.core.config import settings
from app.core.errors import GitHubError
from app.core.logging import get_logger
from app.core.state import IncidentState, failure
from app.pipelines.timeline import plural, record_step, set_current_step
from app.services import supabase as db
from app.services.github.client import load_connection
from app.services.github.fetcher import (
    RepoSnapshot,
    SourceFile,
    frame_path_candidates,
    normalize_path,
    open_snapshot,
    read_file,
    resolve_path,
)

logger = get_logger(__name__)

_HEAD_LINES = 20           # file header shown with every excerpt (imports, constants)
_FULL_FILE_MAX_LINES = 160  # smaller files are shown whole


async def context_node(state: IncidentState) -> Dict[str, Any]:
    if state.get("pending_file_requests") and state.get("repo"):
        return await _fetch_requested(state)
    return await _initial_context(state)


# ================================================================== #
# First pass — stack frames                                            #
# ================================================================== #

async def _initial_context(state: IncidentState) -> Dict[str, Any]:
    incident_id = state.get("incident_id", "unknown")
    user_id = state["user_id"]
    event = state.get("event") or {}
    started = time.perf_counter()
    await set_current_step(state, "Reading source code from GitHub")

    mapping = await asyncio.to_thread(db.resolve_repo_mapping, user_id, event.get("project"))
    connection = await asyncio.to_thread(load_connection, user_id)
    if connection is None or mapping is None:
        note = (
            "GitHub is not connected (or the stored token is no longer valid)."
            if connection is None
            else "No repository is configured for this Sentry project."
        )
        await record_step(state, step="context", kind="tool", status="warning", summary=f"{note} Continuing without source code.")
        return {"repo": None, "repo_note": note, "can_push": False, "source_files": {}, "code_context": {}}

    try:
        snapshot = await asyncio.to_thread(
            open_snapshot, connection.token, mapping["repo_full_name"], mapping.get("branch")
        )
    except GitHubError as exc:
        if exc.retryable:
            await record_step(state, step="context", kind="tool", status="error", summary=str(exc))
            return failure(f"GitHub is temporarily unavailable: {exc}", retryable=True)
        note = f"Could not open {mapping['repo_full_name']}: {exc}"
        await record_step(state, step="context", kind="tool", status="warning", summary=f"{note} Continuing without source code.")
        return {"repo": None, "repo_note": note, "can_push": False, "source_files": {}, "code_context": {}}

    can_push = _can_push(snapshot)
    frames = event.get("frames") or []
    targets = _frame_targets(snapshot, frames, event.get("platform"))

    source_files: Dict[str, Dict[str, Any]] = {}
    code_context: Dict[str, Dict[str, Any]] = {}
    unresolved = len({f.get("filename") or f.get("abs_path") for f in frames}) - len(targets)
    for path, focus_lines in targets.items():
        loaded = await _read(snapshot, path, incident_id)
        if loaded is None:
            continue
        source_files[path] = {"content": loaded.content, "mode": loaded.mode}
        code_context[path] = build_excerpt(loaded, focus_lines, reason="stack trace")

    summary = (
        f"{snapshot.repo_full_name}@{snapshot.branch} ({snapshot.sha[:7]}): read {plural(len(code_context), 'file')} from the stack trace"
    )
    if frames and not code_context:
        summary += " — no frame could be matched to a repository file"
    elif unresolved > 0:
        summary += f"; {plural(unresolved, 'frame location')} not found in the repository"
    if not can_push:
        summary += ". The GitHub token cannot push to this repository, so no PR can be opened"

    await record_step(
        state,
        step="context",
        kind="tool",
        status="ok" if code_context or not frames else "warning",
        summary=summary,
        detail={"files": list(code_context), "sha": snapshot.sha, "tree_complete": snapshot.tree_complete},
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    logger.info("context_node EXIT | incident_id=%s | repo=%s | files=%d", incident_id, snapshot.repo_full_name, len(code_context))
    return {
        "repo": snapshot.to_state(),
        "repo_note": "" if can_push else "The connected GitHub account cannot push to this repository.",
        "can_push": can_push,
        "source_files": source_files,
        "code_context": code_context,
    }


# ================================================================== #
# Follow-up pass — files requested by the Investigator                 #
# ================================================================== #

async def _fetch_requested(state: IncidentState) -> Dict[str, Any]:
    requested = list(state.get("pending_file_requests") or [])
    await set_current_step(state, "Reading more source code")
    started = time.perf_counter()
    try:
        update = await load_more_files(state, requested, reason="requested by Investigator")
    except GitHubError as exc:
        await record_step(state, step="context", kind="tool", status="warning", summary=f"Could not fetch requested files: {exc}")
        return {"pending_file_requests": []}

    added = [p for p in update.get("code_context", {}) if p not in (state.get("code_context") or {})]
    await record_step(
        state,
        step="context",
        kind="tool",
        status="ok" if added else "warning",
        summary=(f"Fetched {plural(len(added), 'requested file')}: {', '.join(added)}" if added else "None of the requested files exist in the repository"),
        detail={"requested": requested, "fetched": added},
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    return {**update, "pending_file_requests": []}


async def load_more_files(state: IncidentState, paths: Iterable[str], *, reason: str) -> Dict[str, Any]:
    """
    Read extra files at the pinned commit and return updated
    ``source_files`` / ``code_context`` dicts.  Shared with the Fix Engineer
    node (it loads the culprit file when the Investigator named one that
    was not in the stack trace).
    """
    repo = state.get("repo")
    source_files = dict(state.get("source_files") or {})
    code_context = dict(state.get("code_context") or {})
    if not repo:
        return {"source_files": source_files, "code_context": code_context}

    connection = await asyncio.to_thread(load_connection, state["user_id"])
    if connection is None:
        return {"source_files": source_files, "code_context": code_context}
    snapshot = await asyncio.to_thread(open_snapshot, connection.token, repo["full_name"], repo["branch"], pinned=repo)

    budget = max(0, settings.MAX_CONTEXT_FILES + 3 - len(source_files))
    for raw in list(paths)[:5]:
        if budget <= 0:
            break
        path_part, _, line_part = (raw or "").partition(":")
        normalized = normalize_path(path_part)
        if not normalized:
            continue
        resolved = await asyncio.to_thread(resolve_path, snapshot, [normalized])
        if not resolved or resolved in source_files:
            continue
        loaded = await _read(snapshot, resolved, state.get("incident_id", "unknown"))
        if loaded is None:
            continue
        focus = [int(line_part)] if line_part.isdigit() else []
        source_files[resolved] = {"content": loaded.content, "mode": loaded.mode}
        code_context[resolved] = build_excerpt(loaded, focus, reason=reason)
        budget -= 1
    return {"source_files": source_files, "code_context": code_context}


# ================================================================== #
# Helpers                                                              #
# ================================================================== #

def _frame_targets(snapshot: RepoSnapshot, frames: List[Dict[str, Any]], platform: Optional[str]) -> Dict[str, List[int]]:
    """Resolve frames (innermost first) to ``{repo_path: [focus lines]}``, capped at MAX_CONTEXT_FILES."""
    targets: Dict[str, List[int]] = {}
    for frame in reversed(frames):
        path = resolve_path(snapshot, frame_path_candidates(frame, platform))
        if not path:
            continue
        if path not in targets:
            if len(targets) >= settings.MAX_CONTEXT_FILES:
                continue
            targets[path] = []
        if frame.get("lineno"):
            targets[path].append(int(frame["lineno"]))
    return targets


async def _read(snapshot: RepoSnapshot, path: str, incident_id: str) -> Optional[SourceFile]:
    try:
        return await asyncio.to_thread(read_file, snapshot, path)
    except GitHubError as exc:
        logger.warning("context_node: could not read %s | incident_id=%s | error=%s", path, incident_id, exc)
        return None


def _can_push(snapshot: RepoSnapshot) -> bool:
    try:
        permissions = snapshot._repo.permissions  # type: ignore[union-attr]
        return bool(permissions and (permissions.push or permissions.admin))
    except Exception:
        return False


def build_excerpt(
    source: SourceFile,
    focus_lines: List[int],
    *,
    reason: str,
    full_file_max_lines: int = _FULL_FILE_MAX_LINES,
) -> Dict[str, Any]:
    """
    Render a numbered excerpt: the whole file when it is small, otherwise the
    header plus a ±CONTEXT_WINDOW_LINES window around each focus line (or the
    first 250 lines when there is no focus line).  Focus lines are marked '>'.
    """
    lines = source.content.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    total = len(lines)
    focus = {line for line in focus_lines if 1 <= line <= total}
    window = settings.CONTEXT_WINDOW_LINES

    if total <= full_file_max_lines:
        ranges = [(1, total)]
    elif not focus:
        ranges = [(1, min(total, 250))]
    else:
        ranges = [(1, min(_HEAD_LINES, total))] + [(max(1, line - window), min(total, line + window)) for line in sorted(focus)]
    merged = _merge_ranges(ranges) if total else []

    rendered: List[str] = []
    previous_end = 0
    for start, end in merged:
        if start > previous_end + 1:
            rendered.append("        ⋮")
        for number in range(start, end + 1):
            marker = ">" if number in focus else " "
            rendered.append(f"{marker}{number:>6} | {lines[number - 1]}")
        previous_end = end
    if previous_end < total:
        rendered.append(f"        ⋮ ({total - previous_end} more lines)")

    return {
        "excerpt": "\n".join(rendered),
        "language": source.language,
        "total_lines": total,
        "focus_lines": sorted(focus),
        "reason": reason,
    }


def _merge_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    merged: List[Tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
