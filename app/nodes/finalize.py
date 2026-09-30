"""
Finalize node — the single place that persists a pipeline run's outcome.

Reads:
    everything produced upstream

Writes:
    status  → "pr_open" | "flagged" | "failed"

Persists:
    fixes      one analysis row per incident: root cause, explanation,
               confidences, the patch (applied or suggested), review notes,
               remediation steps and policy findings
    incidents  final status, classification, severity, confidence,
               repository, token usage, enriched event fields, error text

Persistence errors are raised (not swallowed): the Celery task treats a
database failure as retryable, so an analysis is never silently lost.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.core.state import IncidentState
from app.pipelines.timeline import record_step
from app.services import supabase as db
from app.services.sentry_events import frames_for_storage

logger = get_logger(__name__)


async def finalize_node(state: IncidentState) -> Dict[str, Any]:
    incident_id = state["incident_id"]
    status = _final_status(state)
    investigation = state.get("investigation") or {}
    triage = state.get("triage") or {}
    review = state.get("review") or {}
    event = state.get("event") or {}
    usage = state.get("usage") or {}

    # ---- Analysis row ------------------------------------------------ #
    if investigation:
        fix_row = await asyncio.to_thread(db.save_fix, incident_id, _fix_row(state, status))
        if state.get("pr"):
            await asyncio.to_thread(db.link_pull_request_to_fix, incident_id, fix_row["id"])

    # ---- Incident row ------------------------------------------------ #
    incident_update: Dict[str, Any] = {
        "status": status,
        "current_step": None,
        "completed_at": db.utcnow(),
        "pipeline_error": state.get("error") if status == "failed" else None,
        "llm_input_tokens": int(usage.get("input_tokens", 0)),
        "llm_output_tokens": int(usage.get("output_tokens", 0)),
    }
    if triage.get("category"):
        incident_update["issue_classification"] = triage["category"]
        incident_update["severity"] = triage.get("severity")
    if investigation:
        incident_update["confidence"] = round(float(investigation.get("confidence") or 0), 4)
    repo = state.get("repo")
    if repo:
        incident_update["repo_full_name"] = repo["full_name"]
        incident_update["branch"] = repo["branch"]
    if event:
        incident_update.update(
            error_type=event.get("error_type"),
            error_message=event.get("error_message"),
            culprit=event.get("culprit"),
            platform=event.get("platform"),
            stack_trace=frames_for_storage(event.get("frames") or []),
        )
    await asyncio.to_thread(db.update_incident, incident_id, incident_update)

    summary = {
        "pr_open": f"Pull request #{(state.get('pr') or {}).get('number')} is ready for review.",
        "flagged": "Handed over to a human with a diagnosis and next steps.",
        "failed": f"Analysis failed: {state.get('error') or 'unknown error'}",
    }[status]
    await record_step(
        state,
        step="complete",
        kind="system",
        status={"pr_open": "ok", "flagged": "warning", "failed": "error"}[status],
        summary=summary,
        detail={"input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)},
    )
    logger.info("finalize_node | incident_id=%s | status=%s", incident_id, status)
    return {"status": status}


def _final_status(state: IncidentState) -> str:
    if state.get("status") == "failed":
        return "failed"
    if state.get("pr"):
        return "pr_open"
    return "flagged"


def _fix_row(state: IncidentState, status: str) -> Dict[str, Any]:
    investigation = state.get("investigation") or {}
    review = state.get("review") or {}
    fix = state.get("fix") or {}
    patch = state.get("patch") or {}
    remediation = state.get("remediation")
    diff = patch.get("diff") or state.get("last_diff") or ""

    if state.get("pr"):
        fix_status = "applied"
    elif review.get("verdict") == "reject":
        fix_status = "rejected"
    elif diff:
        fix_status = "pending"
    else:
        fix_status = "not_applicable"

    review_notes: Optional[str] = None
    if review:
        review_notes = review.get("summary") or ""
        if review.get("issues"):
            review_notes += "\n\n" + "\n".join(f"- {issue}" for issue in review["issues"])

    return {
        "root_cause": investigation.get("root_cause") or "",
        "explanation": investigation.get("explanation") or "",
        "confidence": round(float(investigation.get("confidence") or 0), 4),
        "fix_confidence": round(float(review["confidence"]), 4) if review.get("confidence") is not None else None,
        "fix_diff": diff,
        "files_changed": patch.get("files_changed") or _files_in_diff(diff),
        "summary": fix.get("summary") or None,
        "rationale": fix.get("rationale") or None,
        "risk": fix.get("risk") if fix.get("edits") else None,
        "validation_passed": review.get("verdict") == "approve",
        "review_verdict": review.get("verdict"),
        "review_notes": review_notes,
        "remediation": remediation,
        "flag_reason": state.get("flag_reason") if status == "flagged" else None,
        "policy_violations": state.get("policy_violations") or [],
        "status": fix_status,
    }


def _files_in_diff(diff: str) -> list[str]:
    return [line[6:].strip() for line in (diff or "").splitlines() if line.startswith("+++ b/")]
