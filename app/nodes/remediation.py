"""
Remediation node — runs the Remediation Agent for incidents that need a human.

Reads:
    event, triage, investigation, flag_reason, last_diff, repo_note

Writes:
    remediation, usage

Always produces guidance: when the agent is unavailable, a deterministic
checklist for the incident's category is used instead, so a flagged
incident is never left without next steps.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.agents import RemediationAgent
from app.core.errors import AgentOutputError, LLMError
from app.core.logging import get_logger
from app.core.state import IncidentState, add_usage
from app.pipelines.timeline import plural, record_step, set_current_step

logger = get_logger(__name__)


async def remediation_node(state: IncidentState) -> Dict[str, Any]:
    agent = RemediationAgent()
    await set_current_step(state, "Writing next steps")
    reason = state.get("flag_reason") or _default_reason(state)
    if state.get("repo_note") and state["repo_note"] not in reason:
        reason = f"{reason} {state['repo_note']}".strip()

    try:
        result = await agent.run(
            event=state.get("event") or {},
            triage=state.get("triage"),
            investigation=state.get("investigation"),
            flag_reason=reason,
            suggested_diff=state.get("last_diff"),
        )
    except (LLMError, AgentOutputError) as exc:
        logger.warning("remediation_node: agent unavailable — using checklist | incident_id=%s | error=%s", state.get("incident_id"), exc)
        remediation = _fallback(state)
        await record_step(state, step="remediation", kind="agent", status="warning", summary=f"{exc} — used the standard checklist.")
        return {"remediation": remediation, "flag_reason": reason}

    remediation = result.output.model_dump()
    await record_step(
        state,
        step="remediation",
        kind="agent",
        status="ok",
        summary=f"{plural(len(remediation['steps']), 'next step')} for the on-call engineer — {remediation['summary']}",
        result=result,
    )
    return {"remediation": remediation, "flag_reason": reason, "usage": add_usage(state, result.input_tokens, result.output_tokens)}


def _default_reason(state: IncidentState) -> str:
    investigation = state.get("investigation") or {}
    if investigation and not investigation.get("code_fixable"):
        return "The analysis concluded this cannot be fixed with a code change in the repository."
    if investigation:
        return f"Root-cause confidence ({float(investigation.get('confidence') or 0):.0%}) is too low for an automated fix."
    return "The incident needs human review."


_CHECKLISTS: Dict[str, List[str]] = {
    "config_issue": [
        "Find the configuration value named in the error (environment variable, settings file, secret or feature flag).",
        "Compare it across environments (local, staging, production) and correct the missing or wrong value.",
        "Redeploy or restart the affected service so it reads the corrected configuration.",
        "Add start-up validation so a missing value fails the deploy instead of a live request.",
    ],
    "infrastructure": [
        "Check the health and recent events of the dependency in the stack trace (database, cache, queue or external API).",
        "Review deploys, scaling events and network changes around the time of the first occurrence.",
        "Check quotas and resource limits (connections, memory, disk, rate limits) for the affected component.",
        "Add timeouts, retries with backoff and alerting around this dependency.",
    ],
    "data_issue": [
        "Identify the record(s) that triggered the error from the request and breadcrumbs.",
        "Correct or quarantine the bad data and check how it was written.",
        "Add validation at the point where this data enters the system.",
    ],
    "dependency": [
        "Check the changelog and recent version bumps of the library or API in the stack trace.",
        "Pin or roll back the dependency if a recent upgrade introduced the failure.",
        "Add handling for the dependency's error responses at the call site.",
    ],
}


def _fallback(state: IncidentState) -> Dict[str, Any]:
    event = state.get("event") or {}
    category = (state.get("triage") or {}).get("category") or "code_bug"
    investigation = state.get("investigation") or {}
    steps = _CHECKLISTS.get(
        category,
        [
            f"Open {event.get('culprit') or 'the crash site in the stack trace'} and reproduce the failing input.",
            "Handle the failing case explicitly (validation, guard or clear error) and add a regression test.",
            "Deploy and confirm the error stops occurring in Sentry.",
        ],
    )
    summary = investigation.get("root_cause") or f"{event.get('error_type') or 'Error'}: {event.get('error_message') or ''}"
    return {
        "summary": summary[:800],
        "steps": steps,
        "verification": "Confirm in Sentry that no new events arrive for this issue after the change is deployed.",
        "prevention": "Add a regression test for this failure and monitoring for the affected component.",
        "fallback": True,
    }
