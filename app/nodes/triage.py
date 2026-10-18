"""
Triage node — runs the Triage Agent.

Reads:
    event

Writes:
    triage, usage
    (provider outage) status = "failed", error, error_retryable

Triage is a soft signal: when the agent's reply is unusable the node falls
back to a conservative default derived from the Sentry level, records a
warning on the timeline and lets the Investigator (which sees the code)
make the real call.  A provider outage, however, ends the run early as a
retryable failure — every later agent would hit the same outage.
"""

from __future__ import annotations

from typing import Any, Dict

from app.agents import TriageAgent
from app.core.errors import AgentOutputError, LLMError
from app.core.logging import get_logger
from app.core.state import IncidentState, add_usage, failure
from app.pipelines.timeline import record_step, set_current_step

logger = get_logger(__name__)

_SEVERITY_BY_LEVEL = {"fatal": "critical", "error": "high", "warning": "medium", "info": "low", "debug": "low"}


async def triage_node(state: IncidentState) -> Dict[str, Any]:
    incident_id = state.get("incident_id", "unknown")
    event = state.get("event") or {}
    agent = TriageAgent()
    await set_current_step(state, "Classifying the error")

    try:
        result = await agent.run(event=event)
    except LLMError as exc:
        await record_step(state, step="triage", kind="agent", status="error", summary=str(exc))
        if exc.retryable:
            return failure(str(exc), retryable=True)
        return {"triage": _fallback(event, f"Triage unavailable: {exc}")}
    except AgentOutputError as exc:
        logger.warning("triage_node: unusable reply — using fallback | incident_id=%s | error=%s", incident_id, exc)
        await record_step(state, step="triage", kind="agent", status="warning", summary=f"{exc} — used a conservative default.")
        return {"triage": _fallback(event, str(exc))}

    triage = result.output.model_dump()
    await record_step(
        state,
        step="triage",
        kind="agent",
        status="ok",
        summary=f"{triage['category'].replace('_', ' ')} · {triage['severity']} — {triage['summary']}",
        detail={"reasoning": triage["reasoning"], "code_fixable": triage["code_fixable"]},
        result=result,
    )
    logger.info(
        "triage_node EXIT | incident_id=%s | category=%s | severity=%s", incident_id, triage["category"], triage["severity"]
    )
    return {"triage": triage, "usage": add_usage(state, result.input_tokens, result.output_tokens)}


def _fallback(event: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "category": "code_bug",
        "severity": _SEVERITY_BY_LEVEL.get(event.get("level") or "error", "medium"),
        "code_fixable": bool(event.get("frames")),
        "summary": f"{event.get('error_type') or 'Error'}: {(event.get('error_message') or '')[:160]}",
        "reasoning": reason[:500],
        "fallback": True,
    }
