"""
Investigator node — runs the Investigator Agent (root-cause analysis).

Reads:
    event, triage, code_context, repo, investigation_rounds

Writes:
    investigation, investigation_rounds, pending_file_requests, usage
    (on failure) status = "failed", error, error_retryable

If the agent asks for more files and rounds remain, ``pending_file_requests``
is set and the graph routes back to the context tool; the Investigator then
runs again with the extra code.  Requests for files already loaded are
ignored so the loop always makes progress.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.agents import InvestigatorAgent
from app.core.config import settings
from app.core.errors import AgentOutputError, LLMError
from app.core.logging import get_logger
from app.core.state import IncidentState, add_usage, failure
from app.pipelines.timeline import plural, record_step, set_current_step
from app.services.github.fetcher import normalize_path

logger = get_logger(__name__)


async def investigator_node(state: IncidentState) -> Dict[str, Any]:
    incident_id = state.get("incident_id", "unknown")
    round_number = int(state.get("investigation_rounds") or 0) + 1
    max_rounds = settings.MAX_INVESTIGATION_ROUNDS
    agent = InvestigatorAgent()
    await set_current_step(state, "Finding the root cause")

    try:
        result = await agent.run(
            event=state.get("event") or {},
            triage=state.get("triage"),
            code_context=state.get("code_context") or {},
            round_number=round_number,
            max_rounds=max_rounds,
            repo_connected=bool(state.get("repo")),
        )
    except (LLMError, AgentOutputError) as exc:
        retryable = isinstance(exc, LLMError) and exc.retryable
        await record_step(state, step="investigator", kind="agent", status="error", summary=str(exc))
        logger.error("investigator_node FAILED | incident_id=%s | error=%s", incident_id, exc)
        return failure(f"Root-cause analysis failed: {exc}", retryable=retryable)

    investigation = result.output.model_dump()
    requests = _new_file_requests(investigation.get("needs_files") or [], state)
    if round_number >= max_rounds or not state.get("repo"):
        requests = []

    summary = f"{investigation['root_cause']} (confidence {investigation['confidence']:.0%})"
    if requests:
        summary += f" — requested {plural(len(requests), 'more file', 'more files')}: {', '.join(requests)}"
    await record_step(
        state,
        step="investigator",
        kind="agent",
        status="ok",
        summary=summary,
        detail={
            "round": round_number,
            "code_fixable": investigation["code_fixable"],
            "culprit": f"{investigation.get('culprit_file') or ''}:{investigation.get('culprit_line') or ''}".strip(":"),
        },
        result=result,
    )
    logger.info(
        "investigator_node EXIT | incident_id=%s | round=%d | confidence=%.2f | requests=%d",
        incident_id, round_number, investigation["confidence"], len(requests),
    )
    return {
        "investigation": investigation,
        "investigation_rounds": round_number,
        "pending_file_requests": requests,
        "usage": add_usage(state, result.input_tokens, result.output_tokens),
    }


def _new_file_requests(requested: List[str], state: IncidentState) -> List[str]:
    loaded = set((state.get("code_context") or {}).keys())
    fresh: List[str] = []
    for raw in requested:
        path = normalize_path((raw or "").split(":", 1)[0])
        if not path:
            continue
        if path in loaded or any(existing.endswith("/" + path) for existing in loaded):
            continue
        if raw not in fresh:
            fresh.append(raw)
    return fresh[:5]
