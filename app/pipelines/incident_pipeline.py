"""
End-to-end incident analysis pipeline for TrueAI.

Public interface
────────────────
    async def run_incident_pipeline(payload: dict, user_id: str) -> dict

This is the single entry point called by the Celery task
(app/workers/tasks.py).  It:
    1. Generates a unique incident_id (UUID4).
    2. Builds the minimal bootstrap IncidentState.
    3. Invokes the compiled LangGraph pipeline asynchronously.
    4. Logs start, completion, and duration at INFO level.
    5. Returns the final state dict unconditionally — even on total
       failure the caller always receives a well-formed dict with at
       least incident_id, user_id, status, and error populated.

Error contract
──────────────
This function NEVER raises.  All exceptions from the graph execution are
caught, logged at ERROR level with full traceback, and returned as a
failure-state dict.  The Celery task layer decides whether to retry based
on the returned state — it does not have to guard against exceptions here.

Observability
─────────────
Every pipeline run emits three structured log lines:
    1. START  — incident_id, user_id, event_id
    2. END    — incident_id, user_id, event_id, status, action, duration_s
    3. ERROR  — only on unhandled graph exception, with exc_info=True
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict

from app.core.logging import get_logger
from app.core.state import IncidentState, make_initial_state

logger = get_logger(__name__)


async def run_incident_pipeline(
    payload: Dict[str, Any],
    user_id: str,
) -> Dict[str, Any]:
    """
    Execute the full TrueAI incident analysis pipeline and return the result.

    Args:
        payload:  Raw Sentry webhook payload dict.  Passed through as
                  ``raw_payload`` in the initial state; the parser node
                  validates and normalises it.
        user_id:  TrueAI workspace user identifier.  Used for GitHub token
                  lookups and Supabase row ownership throughout the pipeline.

    Returns:
        The final :class:`~app.core.state.IncidentState` as a plain dict.
        Always contains at minimum:
            incident_id : str   — UUID generated at pipeline entry
            user_id     : str   — echoed from argument
            status      : str   — terminal pipeline status
            error       : str   — present only on failure

    Guarantees:
        - Never raises.
        - Always returns a dict (never None).
        - Duration is always logged, even on failure.
    """
    # ---- Identify the run ----------------------------------------- #
    incident_id: str = str(uuid.uuid4())
    event_id: str = (
        payload.get("event_id")
        or payload.get("id")
        or "unknown"
    )

    start_time: float = time.time()

    logger.info(
        "Pipeline START | incident_id=%s | user_id=%s | event_id=%s",
        incident_id,
        user_id,
        event_id,
    )

    # ---- Build bootstrap state ------------------------------------ #
    initial_state: IncidentState = make_initial_state(
        incident_id=incident_id,
        user_id=user_id,
        raw_payload=payload,
    )

    # Insert the incident row into DB first, then update to "processing".
    # Both steps are isolated — a DB failure must not abort the pipeline.
    try:
        import asyncio as _asyncio
        from app.services.supabase import create_incident as _create_incident
        from app.services.supabase import update_incident as _update_incident

        _incident_data = {
            "id": incident_id,
            "user_id": user_id,
            "sentry_event_id": event_id,
            "error_type": (
                payload.get("exception", {})
                .get("values", [{}])[0]
                .get("type", "unknown")
            ),
            "error_message": (
                payload.get("exception", {})
                .get("values", [{}])[0]
                .get("value", "unknown")
            ),
            "stack_trace": payload.get("exception", {}),
            "environment": payload.get("environment", "unknown"),
            "status": "pending",
        }

        _created = await _asyncio.to_thread(_create_incident, _incident_data)
        if _created:
            await _asyncio.to_thread(_update_incident, incident_id, {"status": "processing"})
        else:
            logger.warning(
                "Pipeline: create_incident returned None — skipping status update | "
                "incident_id=%s",
                incident_id,
            )
    except Exception as _exc:
        logger.warning(
            "Pipeline: could not insert/update incident row | incident_id=%s | error=%s",
            incident_id, _exc,
        )

    # ---- Execute graph ------------------------------------------- #
    try:
        # Lazy import to avoid a circular dependency at module load time:
        # incident_pipeline ← (imported by) tasks.py
        # graph             → imports all node modules
        # Any node          → might import from core/ or services/
        # Deferring this import ensures the module dependency graph stays
        # acyclic regardless of future node additions.
        from app.core.graph import incident_graph

        final_state: Dict[str, Any] = await incident_graph.ainvoke(initial_state)

        duration: float = time.time() - start_time
        status: str = final_state.get("status") or "unknown"
        action: str = final_state.get("action") or "none"

        logger.info(
            f"Pipeline COMPLETE | incident_id={incident_id} | status={status} | action={action} | duration={duration:.3f}s"
        )

        # ---- Update incident status based on pipeline action ---- #
        try:
            import asyncio as _asyncio
            from app.services.supabase import update_incident as _update_incident
            if action == "create_pr":
                _db_status = "resolved"
            elif action == "flag_for_review":
                _db_status = "flagged"
            else:
                _db_status = status   # pass through whatever pipeline set
            await _asyncio.to_thread(_update_incident, incident_id, {"status": _db_status})
        except Exception as _exc:
            logger.warning(
                "Pipeline: could not update incident status | incident_id=%s | error=%s",
                incident_id, _exc,
            )

        # Ensure the return value is always a plain dict, not a TypedDict
        # subclass or LangGraph internal wrapper type.
        return dict(final_state)

    # ---- Unhandled graph exception -------------------------------- #
    except Exception as exc:
        duration = time.time() - start_time

        logger.error(
            "Pipeline FAILED (unhandled exception) | incident_id=%s | "
            "user_id=%s | event_id=%s | duration=%.3fs | "
            "error_type=%s | error=%s",
            incident_id,
            user_id,
            event_id,
            duration,
            type(exc).__name__,
            exc,
            exc_info=True,
        )

        # Update incident status to failed in DB.
        try:
            import asyncio as _asyncio
            from app.services.supabase import update_incident as _update_incident
            await _asyncio.to_thread(_update_incident, incident_id, {"status": "failed"})
        except Exception as _db_exc:
            logger.warning(
                "Pipeline: could not set status=failed | incident_id=%s | error=%s",
                incident_id, _db_exc,
            )

        # Return a minimal failure state.  The Celery task checks for
        # incident_id before attempting a Supabase status update, so we
        # must include it even in the catastrophic-failure path.
        return {
            "incident_id": incident_id,
            "user_id": user_id,
            "raw_payload": payload,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "action": None,
        }
