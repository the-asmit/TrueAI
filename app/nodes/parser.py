"""
Parser node — normalises raw Sentry webhook payloads into structured state.

Responsibilities:
- Validate the raw_payload against SentryWebhookPayload schema.
- Extract error_type, error_message, and user-code-only stack frames.
- Build a rich sentry_context dict from event-level metadata and per-frame
  source context lines (pre/post context that Sentry SDK captures).
- Fail fast (status="failed") if the payload contains no user-code frames —
  without frames the entire downstream pipeline has nothing to analyse.

This node never crashes: all exceptions are caught, the error is recorded
in state, and the full (modified) state is always returned.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.core.logging import get_logger
from app.core.state import IncidentState
from app.schemas.webhook import SentryWebhookPayload

logger = get_logger(__name__)


async def parser_node(state: IncidentState) -> IncidentState:
    """
    Parse and normalise the raw Sentry webhook payload stored in *state*.

    Reads:
        raw_payload

    Writes:
        error_type, error_message, stack_frames, sentry_context, status

    On failure writes:
        error, status = "failed"
    """
    state = {**state}   # always work on a full copy
    incident_id = state.get("incident_id", "unknown")
    logger.debug("parser_node ENTRY | incident_id=%s", incident_id)

    try:
        raw_payload: Dict[str, Any] = state.get("raw_payload") or {}

        if not raw_payload:
            state["error"] = "raw_payload is empty — nothing to parse."
            state["status"] = "failed"
            logger.error(
                "parser_node: empty raw_payload | incident_id=%s", incident_id
            )
            return state

        # ---- Schema validation ---------------------------------------- #
        try:
            payload = SentryWebhookPayload.model_validate(raw_payload)
        except Exception as schema_exc:
            state["error"] = (
                f"Sentry payload failed schema validation: "
                f"{type(schema_exc).__name__}: {schema_exc}"
            )
            state["status"] = "failed"
            logger.error(
                "parser_node: schema validation failed | incident_id=%s | error=%s",
                incident_id,
                schema_exc,
            )
            return state

        # ---- Fetch full event from Sentry API if no exception data ---- #
        if not payload.get_stack_frames():
            from app.services.sentry import fetch_sentry_event
            event_id = (
                raw_payload.get("event", {}).get("event_id")
                or raw_payload.get("event_id")
                or raw_payload.get("id")
            )
            project_slug = raw_payload.get("project_slug")
            if event_id and project_slug:
                logger.debug(
                    "parser_node: no frames in webhook payload, fetching full event "
                    "from Sentry API | incident_id=%s | event_id=%s",
                    incident_id, event_id,
                )
                full_event = await fetch_sentry_event(project_slug, event_id)
                if full_event:
                    exception_data = full_event.get("entries", [])
                    for entry in exception_data:
                        if entry.get("type") == "exception":
                            raw_payload = {**raw_payload, "exception": entry.get("data", {})}
                            try:
                                payload = SentryWebhookPayload.model_validate(raw_payload)
                                logger.debug(
                                    "parser_node: full event fetched successfully | "
                                    "incident_id=%s | frames=%d",
                                    incident_id, len(payload.get_stack_frames()),
                                )
                            except Exception as e:
                                logger.warning(
                                    "parser_node: full event schema validation failed | "
                                    "incident_id=%s | error=%s",
                                    incident_id, e,
                                )
                            break

        # ---- Basic error fields --------------------------------------- #
        error_type: str = payload.get_error_type() or "UnknownError"
        error_message: str = payload.get_error_message() or ""

        # ---- User-code frames only ------------------------------------ #
        in_app_frames = payload.get_in_app_frames()
        if not in_app_frames:
            in_app_frames = payload.get_stack_frames()  # fallback to all frames

        if not in_app_frames:
            # No user-code frames means the crash is entirely in third-party
            # or stdlib code — we cannot generate a meaningful fix.
            state["error"] = (
                "No user-code stack frames found in Sentry payload. "
                "All frames are external (third-party / stdlib)."
            )
            state["status"] = "failed"
            logger.error(
                "parser_node: no in-app frames | incident_id=%s | "
                "error_type=%s | total_frames=%d",
                incident_id,
                error_type,
                len(payload.get_stack_frames()),
            )
            return state

        stack_frames: List[Dict[str, Any]] = [f.to_dict() for f in in_app_frames]

        # ---- Sentry context ------------------------------------------ #
        # Collect event-level metadata plus per-frame source context lines
        # into a single dict that the root-cause LLM will receive verbatim.
        sentry_context: Dict[str, Any] = {
            "environment": payload.environment,
            "level": payload.level,
            "platform": payload.platform,
            "release": payload.release,
            "server_name": payload.server_name,
            "transaction": payload.transaction,
            "tags": payload.tags,
            "user": (
                payload.user.model_dump(exclude_none=True) if payload.user else None
            ),
            "request": (
                payload.request.model_dump(exclude_none=True)
                if payload.request
                else None
            ),
            "extra": payload.extra,
            # Per-frame source context lines indexed by "filename:lineno" so
            # the LLM can cross-reference code snippets with frame entries.
            "frame_contexts": _build_frame_contexts(in_app_frames),
        }

        # ---- Write results back --------------------------------------- #
        state["error_type"] = error_type
        state["error_message"] = error_message
        state["stack_frames"] = stack_frames
        state["sentry_context"] = sentry_context
        state["status"] = "processing"

        logger.debug(
            "parser_node EXIT | incident_id=%s | error_type=%s | "
            "user_frames=%d | total_frames=%d",
            incident_id,
            error_type,
            len(in_app_frames),
            len(payload.get_stack_frames()),
        )
        return state

    except Exception as exc:
        state["error"] = f"parser_node unhandled exception: {type(exc).__name__}: {exc}"
        state["status"] = "failed"
        logger.error(
            "parser_node EXCEPTION | incident_id=%s | error=%s",
            incident_id,
            exc,
            exc_info=True,
        )
        return state


# ------------------------------------------------------------------ #
# Internal helpers                                                     #
# ------------------------------------------------------------------ #

def _build_frame_contexts(frames) -> Dict[str, Any]:
    """
    Build a dict of per-frame source context keyed by ``"filename:lineno"``.

    Having inline pre/post context in sentry_context means the root-cause
    prompt can reference exact source lines without waiting for GitHub to
    return them, which is useful for files that GitHub cannot reach.
    """
    contexts: Dict[str, Any] = {}
    for frame in frames:
        key = f"{frame.filename or 'unknown'}:{frame.lineno or '?'}"
        contexts[key] = {
            "function": frame.function,
            "context_line": frame.context_line,
            "pre_context": frame.pre_context,
            "post_context": frame.post_context,
        }
    return contexts
