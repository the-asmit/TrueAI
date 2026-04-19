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

    start: float = time.time()

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

        duration: float = time.time() - start
        status: str = final_state.get("status") or "unknown"
        action: str = final_state.get("action") or "none"

        logger.info(
            "Pipeline COMPLETE | incident_id=%s | user_id=%s | event_id=%s | "
            "status=%s | action=%s | duration=%.3fs",
            incident_id,
            user_id,
            event_id,
            status,
            action,
            duration,
        )

        # Ensure the return value is always a plain dict, not a TypedDict
        # subclass or LangGraph internal wrapper type.
        return dict(final_state)

    # ---- Unhandled graph exception -------------------------------- #
    except Exception as exc:
        duration = time.time() - start

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
            exc_info=True,   # attach full traceback to the log record
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
