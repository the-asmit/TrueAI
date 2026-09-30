"""
End-to-end incident analysis pipeline entry point.

Public interface
────────────────
    async def run_incident_pipeline(incident_id: str) -> dict

Called by the Celery task.  The incident row (with the scrubbed Sentry
payload) was created by the webhook, so only its id travels through the
queue — retries and re-analysis always operate on the same incident.

Steps:
    1. Load the incident; skip it if a user already resolved/ignored it.
    2. Mark it ``processing`` and clear the previous run's timeline.
    3. Run the LangGraph agent pipeline under PIPELINE_TIMEOUT_SECONDS.
    4. Return the final state.  The ``finalize`` node persists results;
       failures that happen outside the graph are persisted here.

Error contract
──────────────
Never raises.  The returned dict always has ``status``; when it is
``failed``, ``error_retryable`` tells the Celery task whether retrying
could help (provider outage, database hiccup, timeout) or not.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from app.core.config import settings
from app.core.errors import DatabaseError, TrueAIError
from app.core.logging import get_logger, incident_id_var
from app.core.state import make_initial_state
from app.services import supabase as db

logger = get_logger(__name__)


async def run_incident_pipeline(incident_id: str) -> Dict[str, Any]:
    started = time.time()
    token = incident_id_var.set(incident_id)
    try:
        try:
            row = await asyncio.to_thread(db.get_incident_for_worker, incident_id)
        except DatabaseError as exc:
            return {"incident_id": incident_id, "status": "failed", "error": str(exc), "error_retryable": True}
        if row is None:
            logger.warning("Pipeline: incident not found (deleted?) | incident_id=%s", incident_id)
            return {"incident_id": incident_id, "status": "missing"}
        if row.get("status") not in ("queued", "processing"):
            # Already finished (or resolved/ignored by a user) — a duplicate delivery.
            logger.info("Pipeline: skipping incident in status=%s | incident_id=%s", row.get("status"), incident_id)
            return {"incident_id": incident_id, "status": "skipped"}

        user_id = row["user_id"]
        logger.info("Pipeline START | incident_id=%s | user_id=%s | event_id=%s", incident_id, user_id, row.get("sentry_event_id"))
        try:
            await asyncio.to_thread(db.delete_steps, incident_id)
            await asyncio.to_thread(
                db.update_incident,
                incident_id,
                {
                    "status": "processing",
                    "started_at": db.utcnow(),
                    "completed_at": None,
                    "attempts": int(row.get("attempts") or 0) + 1,
                    "current_step": "Starting analysis",
                    "pipeline_error": None,
                },
            )
        except DatabaseError as exc:
            return {"incident_id": incident_id, "status": "failed", "error": str(exc), "error_retryable": True}

        initial_state = make_initial_state(
            incident_id=incident_id,
            user_id=user_id,
            raw_payload=row.get("raw_payload") or {},
            run=int(row.get("analysis_run") or 1),
        )

        from app.core.graph import RECURSION_LIMIT, incident_graph

        try:
            final_state = await asyncio.wait_for(
                incident_graph.ainvoke(initial_state, config={"recursion_limit": RECURSION_LIMIT}),
                timeout=settings.PIPELINE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            message = f"Analysis did not finish within {settings.PIPELINE_TIMEOUT_SECONDS} seconds."
            await _mark_failed(incident_id, message)
            return {"incident_id": incident_id, "status": "failed", "error": message, "error_retryable": True}
        except TrueAIError as exc:
            await _mark_failed(incident_id, str(exc))
            return {"incident_id": incident_id, "status": "failed", "error": str(exc), "error_retryable": exc.retryable}
        except Exception as exc:
            logger.error("Pipeline crashed | incident_id=%s | error=%s", incident_id, exc, exc_info=True)
            message = f"Internal error during analysis ({type(exc).__name__})."
            await _mark_failed(incident_id, message)
            return {"incident_id": incident_id, "status": "failed", "error": message, "error_retryable": False}

        result = dict(final_state)
        logger.info(
            "Pipeline COMPLETE | incident_id=%s | status=%s | duration=%.1fs | tokens_in=%s | tokens_out=%s",
            incident_id,
            result.get("status"),
            time.time() - started,
            (result.get("usage") or {}).get("input_tokens"),
            (result.get("usage") or {}).get("output_tokens"),
        )
        return result
    finally:
        incident_id_var.reset(token)


async def _mark_failed(incident_id: str, message: str) -> None:
    try:
        await asyncio.to_thread(
            db.update_incident,
            incident_id,
            {"status": "failed", "pipeline_error": message[:1000], "current_step": None, "completed_at": db.utcnow()},
        )
    except Exception as exc:
        logger.error("Pipeline: could not record failure | incident_id=%s | error=%s", incident_id, exc)
