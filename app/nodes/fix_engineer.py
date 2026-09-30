"""
Fix Engineer node — runs the Fix Engineer Agent, then applies and checks its edits.

Reads:
    event, investigation, repo, source_files, code_context, fix_attempts,
    fix_feedback, last_diff

Writes:
    fix, patch, last_diff, fix_attempts, fix_feedback, policy_violations,
    check_notes, usage, (sometimes) source_files / code_context
    (no safe fix possible) action = "flag_for_review", flag_reason
    (provider outage) status = "failed", error, error_retryable

Self-correction loop
────────────────────
The agent's edits go through the deterministic patch engine:
    apply edits → syntax check → policy guard-rails
Any problem is turned into precise feedback and, while attempts remain,
``patch`` is left empty so the graph routes back here for another attempt.
A clean patch continues to the Reviewer Agent.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.agents import FixEngineerAgent
from app.core.config import settings
from app.core.errors import AgentOutputError, LLMError, PatchError
from app.core.logging import get_logger
from app.core.state import IncidentState, add_usage, failure
from app.nodes.context import build_excerpt, load_more_files
from app.pipelines.timeline import plural, record_step, set_current_step
from app.services.github.fetcher import SourceFile, normalize_path
from app.services.patching import FileEdit, apply_edits, check_policy, validate_syntax

logger = get_logger(__name__)

_FIX_VIEW_FULL_FILE_LINES = 400


async def fix_engineer_node(state: IncidentState) -> Dict[str, Any]:
    incident_id = state.get("incident_id", "unknown")
    attempt = int(state.get("fix_attempts") or 0) + 1
    max_attempts = settings.MAX_FIX_ATTEMPTS
    investigation = state.get("investigation") or {}
    agent = FixEngineerAgent()
    await set_current_step(state, f"{agent.title} (attempt {attempt})")

    updates: Dict[str, Any] = {"fix_attempts": attempt}
    source_files = dict(state.get("source_files") or {})

    # ---- Make sure the file the Investigator blamed is loaded -------- #
    culprit = normalize_path(investigation.get("culprit_file") or "")
    if culprit and state.get("repo") and not any(p == culprit or p.endswith("/" + culprit) for p in source_files):
        try:
            loaded = await load_more_files(state, [culprit], reason="named by the Investigator")
            source_files = loaded["source_files"]
            updates.update(loaded)
        except Exception as exc:
            logger.warning("fix_engineer_node: could not load culprit file %s | incident_id=%s | error=%s", culprit, incident_id, exc)

    if not source_files:
        reason = "No source files could be loaded from the repository, so no code change can be written."
        await record_step(state, step="fix_engineer", kind="agent", status="skipped", summary=reason)
        return {**updates, "action": "flag_for_review", "flag_reason": reason}

    fix_view = _fix_view(source_files, state, culprit)
    try:
        result = await agent.run(
            event=state.get("event") or {},
            investigation=investigation,
            code_context=fix_view,
            attempt=attempt,
            max_attempts=max_attempts,
            feedback=list(state.get("fix_feedback") or []),
            previous_diff=state.get("last_diff"),
        )
    except LLMError as exc:
        await record_step(state, step="fix_engineer", kind="agent", status="error", summary=str(exc))
        if exc.retryable:
            return {**updates, **failure(f"Fix generation failed: {exc}", retryable=True)}
        return {**updates, "action": "flag_for_review", "flag_reason": f"The Fix Engineer could not run: {exc}"}
    except AgentOutputError as exc:
        await record_step(state, step="fix_engineer", kind="agent", status="error", summary=str(exc))
        return {**updates, "action": "flag_for_review", "flag_reason": f"The Fix Engineer's reply was unusable: {exc}"}

    fix = result.output.model_dump()
    updates["fix"] = fix
    updates["usage"] = add_usage(state, result.input_tokens, result.output_tokens)

    if fix.get("cannot_fix"):
        reason = f"The Fix Engineer concluded no safe code change exists: {fix['cannot_fix']}"
        await record_step(state, step="fix_engineer", kind="agent", status="warning", summary=reason, result=result)
        return {**updates, "action": "flag_for_review", "flag_reason": reason}

    await record_step(
        state,
        step="fix_engineer",
        kind="agent",
        status="ok",
        summary=f"{fix['summary']} ({plural(len(fix['edits']), 'edit')}, risk {fix['risk']})",
        detail={"attempt": attempt, "rationale": fix["rationale"]},
        result=result,
    )

    # ---- Deterministic checks: apply → syntax → policy ---------------- #
    originals = {path: item["content"] for path, item in source_files.items()}
    edits = [FileEdit(path=_match_path(e["path"], originals), search=e["find_exact"], replace=e["replace_with"]) for e in fix["edits"]]
    problems: List[str] = []
    patch = None
    try:
        patch = apply_edits(edits, originals)
        for path in patch.files_changed:
            syntax_error = validate_syntax(path, originals[path], patch.files[path])
            if syntax_error:
                problems.append(f"The change leaves {path} with {syntax_error}.")
    except PatchError as exc:
        problems.append(str(exc))

    violations = check_policy(patch, originals) if patch and not problems else []
    if patch:
        updates["last_diff"] = patch.diff

    if problems or violations:
        feedback = problems + [f"Policy: {v} Produce a fix without this." for v in violations]
        updates["fix_feedback"] = list(state.get("fix_feedback") or []) + feedback
        updates["patch"] = {}
        await record_step(
            state,
            step="patch",
            kind="tool",
            status="error" if problems else "warning",
            summary="; ".join(feedback)[:900],
            detail={"attempt": attempt},
        )
        if attempt >= max_attempts:
            updates["policy_violations"] = violations
            reason = (
                "The proposed change was blocked by TrueAI's safety policy: " + "; ".join(violations)
                if violations and not problems
                else "The Fix Engineer could not produce a change that applies cleanly: " + "; ".join(problems)
            )
            return {**updates, "action": "flag_for_review", "flag_reason": reason[:1500]}
        return updates

    check_notes = [
        f"Edits applied cleanly to {', '.join(patch.files_changed)} (+{patch.added_lines} / -{patch.removed_lines} lines).",
        "Syntax check passed." if any(p.endswith((".py", ".json", ".yml", ".yaml", ".toml")) for p in patch.files_changed)
        else "No syntax checker is available for these file types.",
        "Safety policy checks passed (size limits, protected paths, dangerous constructs).",
    ]
    await record_step(state, step="patch", kind="tool", status="ok", summary=check_notes[0], detail={"files": patch.files_changed})
    return {
        **updates,
        "patch": {
            "diff": patch.diff,
            "files_changed": patch.files_changed,
            "files": patch.files,
            "added_lines": patch.added_lines,
            "removed_lines": patch.removed_lines,
        },
        "policy_violations": [],
        "check_notes": check_notes,
    }


def _fix_view(source_files: Dict[str, Dict[str, Any]], state: IncidentState, culprit: str | None) -> Dict[str, Dict[str, Any]]:
    """Editable files for the prompt: whole files up to 400 lines, excerpts otherwise; culprit first."""
    code_context = state.get("code_context") or {}
    ordered = sorted(source_files, key=lambda p: 0 if culprit and (p == culprit or p.endswith("/" + culprit)) else 1)
    view: Dict[str, Dict[str, Any]] = {}
    for path in ordered:
        focus = list((code_context.get(path) or {}).get("focus_lines") or [])
        investigation = state.get("investigation") or {}
        if investigation.get("culprit_line") and culprit and (path == culprit or path.endswith("/" + culprit)):
            focus.append(int(investigation["culprit_line"]))
        source = SourceFile(path=path, content=source_files[path]["content"])
        view[path] = build_excerpt(source, focus, reason="editable", full_file_max_lines=_FIX_VIEW_FULL_FILE_LINES)
    return view


def _match_path(proposed: str, originals: Dict[str, str]) -> str:
    """Accept a path the agent shortened or prefixed, as long as it maps to exactly one loaded file."""
    cleaned = normalize_path(proposed) or proposed
    if cleaned in originals:
        return cleaned
    matches = [p for p in originals if p.endswith("/" + cleaned) or cleaned.endswith("/" + p)]
    return matches[0] if len(matches) == 1 else cleaned
