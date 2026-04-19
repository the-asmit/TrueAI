"""
Deduplication node — prevents the same Sentry event from being analysed twice.

Uses a Redis atomic SET NX EX operation (via app/services/redis.py) so that
even under concurrent webhook delivery (Sentry retries the same event up to
3 times on 5xx responses) exactly one pipeline run proceeds.

Fail-open design: if Redis is unreachable, is_duplicate() already returns
False (logged in the Redis service layer).  This node treats any exception
from the Redis call as non-duplicate — it is always safer to process a
potential duplicate than to silently drop a real incident.

This node never crashes: all exceptions are caught and the full state is
always returned.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.state import IncidentState

logger = get_logger(__name__)

# TTL for dedup keys: 24 hours.  Sentry can send the same event multiple
# times within minutes of the original delivery; after 24 hours re-processing
# the same event is intentional (e.g. a re-triggered alert).
_DEDUP_TTL_SECONDS: int = 86_400


async def dedup_node(state: IncidentState) -> IncidentState:
    """
    Check whether this Sentry event has already entered the pipeline.

    Reads:
        raw_payload  (for event_id),  incident_id  (fallback key)

    Writes:
        status = "duplicate"  when the event is a duplicate (exits pipeline)
        No writes on the non-duplicate path.

    Never writes error / status = "failed" — dedup failure is non-fatal.
    """
    state = {**state}
    incident_id = state.get("incident_id", "unknown")
    logger.debug("dedup_node ENTRY | incident_id=%s", incident_id)

    try:
        # Resolve the dedup key.  Prefer the Sentry event_id because it is
        # stable across Sentry's own retries.  Fall back to incident_id
        # (a UUID we generated) which is unique per pipeline run — this means
        # the fallback never deduplicates, which is the safe choice.
        raw_payload = state.get("raw_payload") or {}
        event_id: str = (
            raw_payload.get("event_id")
            or raw_payload.get("id")
            or ""
        )

        if not event_id:
            logger.warning(
                "dedup_node: no event_id in payload, skipping dedup check | "
                "incident_id=%s",
                incident_id,
            )
            return state

        # Import lazily to defer Redis connection until first use.
        from app.services.redis import is_duplicate

        if is_duplicate(event_id, ttl_seconds=_DEDUP_TTL_SECONDS):
            state["status"] = "duplicate"
            logger.info(
                "dedup_node: duplicate detected — stopping pipeline | "
                "incident_id=%s | event_id=%s",
                incident_id,
                event_id,
            )
            return state

        logger.debug(
            "dedup_node EXIT | incident_id=%s | event_id=%s | is_duplicate=False",
            incident_id,
            event_id,
        )
        return state

    except Exception as exc:
        # Fail open: log the error but let the pipeline continue.  Stopping
        # processing because of a Redis hiccup is worse than a rare duplicate.
        logger.error(
            "dedup_node EXCEPTION (failing open) | incident_id=%s | "
            "error=%s — %s",
            incident_id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        return state
