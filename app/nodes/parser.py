"""
Parser node — turns the stored Sentry payload into a normalised event.

Reads:
    raw_payload, user_id

Writes:
    event
    (on failure) status = "failed", error

When the webhook carried no stack trace (Sentry's "issue" webhook, or a
minimal alert) the full event is fetched from the Sentry API using the
user's Sentry credentials.  A missing stack trace is NOT fatal: the agents
can still analyse the error message and Sentry context, they just cannot
propose a code patch without source locations.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from app.core.logging import get_logger
from app.core.state import IncidentState, failure
from app.pipelines.timeline import plural, record_step, set_current_step
from app.services import sentry as sentry_api
from app.services.sentry_events import flatten_api_event, normalize_event

logger = get_logger(__name__)


async def parser_node(state: IncidentState) -> Dict[str, Any]:
    incident_id = state.get("incident_id", "unknown")
    started = time.perf_counter()
    await set_current_step(state, "Reading the Sentry event")

    raw_payload = state.get("raw_payload") or {}
    if not raw_payload or raw_payload.get("truncated"):
        message = "The stored Sentry payload is empty or was too large to keep; nothing to analyse."
        await record_step(state, step="parse", kind="tool", status="error", summary=message)
        return failure(message)

    try:
        event = normalize_event(raw_payload)
    except Exception as exc:
        logger.error("parser_node: normalisation failed | incident_id=%s | error=%s", incident_id, exc, exc_info=True)
        message = f"The Sentry payload could not be parsed ({type(exc).__name__})."
        await record_step(state, step="parse", kind="tool", status="error", summary=message)
        return failure(message)

    enriched = False
    if not event.get("frames"):
        event, enriched = await _enrich_from_sentry_api(state, event)

    frames = event.get("frames") or []
    if frames:
        summary = f"{event['error_type']} with {plural(len(frames), 'application frame')}"
        if event.get("in_app_fallback"):
            summary += " (Sentry marked no frames as in-app; vendor frames were filtered heuristically)"
        status = "ok"
    else:
        summary = f"{event['error_type']} — no stack trace available, analysis will rely on the error details"
        status = "warning"
    if enriched:
        summary += "; full event fetched from the Sentry API"

    await record_step(
        state,
        step="parse",
        kind="tool",
        status=status,
        summary=summary,
        detail={"platform": event.get("platform"), "project": event.get("project"), "total_frames": event.get("total_frames")},
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    logger.info("parser_node EXIT | incident_id=%s | error_type=%s | frames=%d", incident_id, event["error_type"], len(frames))
    return {"event": event}


async def _enrich_from_sentry_api(state: IncidentState, event: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    """Fetch the complete event when the webhook had no frames. Returns (event, enriched)."""
    try:
        creds = await asyncio.to_thread(sentry_api.resolve_credentials, state["user_id"])
    except Exception as exc:
        logger.warning("parser_node: could not load Sentry credentials | incident_id=%s | error=%s", state.get("incident_id"), exc)
        return event, False
    if creds is None:
        return event, False

    full = None
    if event.get("event_id") and event.get("project"):
        full = await sentry_api.fetch_event(creds, event["project"], event["event_id"])
    if full is None and event.get("issue_id"):
        full = await sentry_api.fetch_latest_issue_event(creds, event["issue_id"])
    if not full:
        return event, False

    fetched = normalize_event({"event": flatten_api_event(full)})
    if not fetched.get("frames"):
        return event, False
    # Keep identity from the webhook (issue grouping) and take evidence from the API.
    for key in ("issue_id", "issue_url", "project", "fingerprint"):
        if event.get(key):
            fetched[key] = event[key]
    return fetched, True
