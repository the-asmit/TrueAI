"""
Pipeline timeline — what each agent and tool did, persisted for the dashboard.

Every node records one or more steps in ``pipeline_steps`` (agent, model,
duration, tokens, outcome, short summary) and updates the incident's
``current_step`` so the dashboard can show live progress.

Recording is best-effort: a timeline write failure is logged and never
fails the pipeline.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from app.agents.base import AgentResult
from app.core.logging import get_logger
from app.core.state import IncidentState

logger = get_logger(__name__)


def plural(count: int, noun: str, plural_noun: Optional[str] = None) -> str:
    """``plural(1, "file")`` -> "1 file"; ``plural(3, "file")`` -> "3 files" (for timeline summaries)."""
    return f"{count} {noun if count == 1 else (plural_noun or noun + 's')}"


async def set_current_step(state: IncidentState, label: Optional[str]) -> None:
    from app.services import supabase as db

    try:
        await asyncio.to_thread(db.update_incident, state["incident_id"], {"current_step": label})
    except Exception as exc:
        logger.warning("timeline: could not update current_step | incident_id=%s | error=%s", state.get("incident_id"), exc)


async def record_step(
    state: IncidentState,
    *,
    step: str,
    kind: str,
    status: str,
    summary: str,
    detail: Optional[Dict[str, Any]] = None,
    result: Optional[AgentResult] = None,
    duration_ms: Optional[int] = None,
) -> None:
    """Persist one timeline entry. ``kind`` is agent | tool | system; ``status`` is ok | warning | error | skipped."""
    from app.services import supabase as db

    row: Dict[str, Any] = {
        "incident_id": state["incident_id"],
        "user_id": state["user_id"],
        "run": state.get("run", 1),
        "step": step,
        "kind": kind,
        "status": status,
        "summary": (summary or "")[:1000],
        "detail": detail or None,
        "duration_ms": duration_ms,
    }
    if result is not None:
        row.update(
            provider=result.spec.provider,
            model=result.spec.model,
            duration_ms=result.duration_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
    try:
        await asyncio.to_thread(db.add_step, row)
    except Exception as exc:
        logger.warning("timeline: could not record step '%s' | incident_id=%s | error=%s", step, state.get("incident_id"), exc)
