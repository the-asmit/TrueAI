"""
Reviewer node — runs the Reviewer Agent on the applied patch.

Reads:
    event, investigation, fix, patch, source_files, code_context,
    check_notes, fix_attempts, fix_feedback

Writes:
    review, usage
    (revise, attempts left) fix_feedback, patch = {}      → back to the Fix Engineer
    (reject / out of attempts / reviewer unavailable) action = "flag_for_review", flag_reason

Unreviewed code is never auto-merged into a PR: if the Reviewer cannot run,
the patch is kept as a suggestion on the incident and a human decides.
"""

from __future__ import annotations

from typing import Any, Dict

from app.agents import ReviewerAgent
from app.core.config import settings
from app.core.errors import AgentOutputError, LLMError
from app.core.logging import get_logger
from app.core.state import IncidentState, add_usage
from app.nodes.context import build_excerpt
from app.pipelines.timeline import record_step, set_current_step
from app.services.github.fetcher import SourceFile

logger = get_logger(__name__)


async def reviewer_node(state: IncidentState) -> Dict[str, Any]:
    incident_id = state.get("incident_id", "unknown")
    attempt = int(state.get("fix_attempts") or 1)
    max_attempts = settings.MAX_FIX_ATTEMPTS
    patch = state.get("patch") or {}
    agent = ReviewerAgent()
    await set_current_step(state, f"{agent.title} (attempt {attempt})")

    # The Reviewer sees the ORIGINAL code of every changed file.
    source_files = state.get("source_files") or {}
    code_context = state.get("code_context") or {}
    original_view = {
        path: build_excerpt(
            SourceFile(path=path, content=source_files[path]["content"]),
            list((code_context.get(path) or {}).get("focus_lines") or []),
            reason="original",
            full_file_max_lines=300,
        )
        for path in patch.get("files_changed") or []
        if path in source_files
    }

    try:
        result = await agent.run(
            event=state.get("event") or {},
            investigation=state.get("investigation") or {},
            fix=state.get("fix") or {},
            diff=patch.get("diff") or "",
            code_context=original_view,
            automated_checks=list(state.get("check_notes") or []),
            attempt=attempt,
            max_attempts=max_attempts,
        )
    except (LLMError, AgentOutputError) as exc:
        await record_step(state, step="reviewer", kind="agent", status="error", summary=str(exc))
        return {
            "action": "flag_for_review",
            "flag_reason": f"The automated review could not be completed ({exc}); the patch is attached as a suggestion only.",
        }

    review = result.output.model_dump()
    updates: Dict[str, Any] = {"review": review, "usage": add_usage(state, result.input_tokens, result.output_tokens)}
    verdict = review["verdict"]

    await record_step(
        state,
        step="reviewer",
        kind="agent",
        status={"approve": "ok", "revise": "warning", "reject": "error"}[verdict],
        summary=f"{verdict.capitalize()} (confidence {review['confidence']:.0%}) — {review['summary']}",
        detail={"attempt": attempt, "issues": review["issues"]},
        result=result,
    )
    logger.info("reviewer_node EXIT | incident_id=%s | attempt=%d | verdict=%s", incident_id, attempt, verdict)

    if verdict == "approve":
        return updates
    if verdict == "revise" and attempt < max_attempts:
        instructions = review["revision_instructions"] or "Address the review issues."
        feedback = [f"Reviewer: {instructions}"] + [f"Reviewer issue: {issue}" for issue in review["issues"][:4]]
        return {**updates, "fix_feedback": list(state.get("fix_feedback") or []) + feedback, "patch": {}}

    reason = (
        f"The Reviewer Agent rejected the proposed fix: {review['summary']}"
        if verdict == "reject"
        else f"The Reviewer Agent still requested changes after {attempt} attempts: {review['summary']}"
    )
    return {**updates, "action": "flag_for_review", "flag_reason": reason}
