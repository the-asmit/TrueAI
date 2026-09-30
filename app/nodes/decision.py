"""
Decision node — pure logic: open a pull request or hand over to a human.

Reads:
    investigation, review, fix, patch, policy_violations, repo, can_push

Writes:
    action = "create_pr" | "flag_for_review"
    flag_reason (when flagging)

A pull request is opened only when EVERY condition holds:
    - the Reviewer approved the patch
    - the Reviewer's confidence  ≥ CONFIDENCE_AUTO_PR_THRESHOLD
    - the Investigator's confidence ≥ CONFIDENCE_AUTO_PR_THRESHOLD
    - the Fix Engineer did not rate the change high-risk
    - no safety-policy violation
    - a repository is connected and the token can push to it

Any unmet condition flags the incident; the reasons are recorded verbatim
so the dashboard can say exactly why no PR was opened.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.core.config import settings
from app.core.logging import get_logger
from app.core.state import IncidentState
from app.pipelines.timeline import record_step

logger = get_logger(__name__)


async def decision_node(state: IncidentState) -> Dict[str, Any]:
    threshold = settings.CONFIDENCE_AUTO_PR_THRESHOLD
    review = state.get("review") or {}
    investigation = state.get("investigation") or {}
    fix = state.get("fix") or {}
    patch = state.get("patch") or {}

    blockers: List[str] = []
    if review.get("verdict") != "approve":
        blockers.append("the Reviewer did not approve the patch")
    if float(review.get("confidence") or 0) < threshold:
        blockers.append(f"review confidence {float(review.get('confidence') or 0):.0%} is below the {threshold:.0%} auto-PR threshold")
    if float(investigation.get("confidence") or 0) < threshold:
        blockers.append(
            f"root-cause confidence {float(investigation.get('confidence') or 0):.0%} is below the {threshold:.0%} auto-PR threshold"
        )
    if fix.get("risk") == "high":
        blockers.append("the Fix Engineer rated the change high-risk")
    if state.get("policy_violations"):
        blockers.append("the patch violates TrueAI's safety policy")
    if not patch.get("files"):
        blockers.append("there is no applied patch")
    if not state.get("repo"):
        blockers.append("no repository is connected")
    elif not state.get("can_push"):
        blockers.append("the connected GitHub account cannot push to the repository")

    if blockers:
        reason = "No pull request was opened because " + "; ".join(blockers) + ". The patch is attached as a suggestion."
        await record_step(state, step="decision", kind="system", status="warning", summary=reason)
        logger.info("decision_node | incident_id=%s | action=flag_for_review | blockers=%d", state.get("incident_id"), len(blockers))
        return {"action": "flag_for_review", "flag_reason": reason}

    await record_step(
        state,
        step="decision",
        kind="system",
        status="ok",
        summary=f"All checks passed (review {float(review['confidence']):.0%}, root cause {float(investigation['confidence']):.0%}) — opening a pull request.",
    )
    logger.info("decision_node | incident_id=%s | action=create_pr", state.get("incident_id"))
    return {"action": "create_pr"}
