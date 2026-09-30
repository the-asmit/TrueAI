"""
Sentry webhook ingestion.

Endpoint: POST /webhook/sentry?key=<api key>

Processing order
────────────────
1. Rate limits — per client IP (stops key brute-forcing) and per API key.
2. Body size limit (WEBHOOK_MAX_BODY_BYTES) → 413.
3. API key → user.  A database outage answers 503 so Sentry retries,
   rather than 401 which would look like a bad key.
4. Signature — ``sentry-hook-signature`` (HMAC-SHA256 of the raw body) is
   verified with the user's webhook secret, or the global
   SENTRY_WEBHOOK_SECRET, whenever one is configured.
5. Resource filter — only new errors/issues are analysed; other hooks
   (issue resolved, installation, metric alerts…) are acknowledged.
6. Deduplication — the same Sentry event id is accepted once per 24 h.
7. Grouping — a repeat of an issue that is still open (queued, analysing,
   PR open or flagged) within INCIDENT_GROUPING_WINDOW_HOURS increments
   that incident's occurrence count instead of starting a new analysis.
8. The incident row (scrubbed payload) is created and the job enqueued.
   Returns 202 immediately.

If the queue is down, the incident is still stored as ``queued`` and the
worker's recovery task picks it up — an accepted event is never lost.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.auth.api_keys import looks_like_api_key, resolve_api_key
from app.core.config import settings
from app.core.errors import DatabaseError, SentryAPIError
from app.core.logging import get_logger
from app.core.rate_limit import client_ip, enforce
from app.services import redis as redis_svc
from app.services import supabase as db
from app.services.sentry import resolve_webhook_secret
from app.services.sentry_events import frames_for_storage, normalize_event, payload_for_storage, should_process

logger = get_logger(__name__)

router = APIRouter()

_EVENT_DEDUP_TTL = 86_400


@router.post("/sentry", status_code=status.HTTP_202_ACCEPTED, summary="Receive a Sentry webhook")
async def receive_sentry_webhook(
    request: Request,
    key: Optional[str] = Query(default=None, max_length=200),
    sentry_hook_resource: Optional[str] = Header(default=None, alias="sentry-hook-resource"),
    sentry_hook_signature: Optional[str] = Header(default=None, alias="sentry-hook-signature"),
) -> JSONResponse:
    # ---- 1. Rate limits ------------------------------------------------- #
    await run_in_threadpool(enforce, "webhook-ip", client_ip(request), max(120, settings.RATE_LIMIT_PER_MINUTE * 4), 60)
    if not key or not looks_like_api_key(key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or malformed webhook key.")
    await run_in_threadpool(enforce, "webhook-key", key, settings.RATE_LIMIT_PER_MINUTE, 60)

    # ---- 2. Body (size-capped) ------------------------------------------ #
    raw_body = await _read_body(request)

    # ---- 3. Authenticate ------------------------------------------------ #
    try:
        user_id = await run_in_threadpool(resolve_api_key, key)
    except DatabaseError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Temporarily unavailable.")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked webhook key.")

    # ---- 4. Signature ---------------------------------------------------- #
    try:
        secret = await run_in_threadpool(resolve_webhook_secret, user_id)
    except (DatabaseError, SentryAPIError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Temporarily unavailable.")
    if secret and not _signature_valid(raw_body, sentry_hook_signature, secret):
        logger.warning("Webhook: signature check failed | user_id=%s", user_id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Webhook signature verification failed.")

    # ---- 5. Parse & filter ---------------------------------------------- #
    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError, RecursionError):  # RecursionError: absurdly nested JSON
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Request body must be valid JSON.")
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Request body must be a JSON object.")

    process, reason = should_process(sentry_hook_resource, payload)
    if not process:
        return _accepted(processed=False, reason=reason)

    event = normalize_event(payload)
    event_id = event.get("event_id")

    # ---- 6. Deduplicate -------------------------------------------------- #
    if event_id and await run_in_threadpool(redis_svc.claim_once, f"event:{user_id}:{event_id}", _EVENT_DEDUP_TTL) is False:
        logger.info("Webhook: duplicate delivery ignored | user_id=%s | event_id=%s", user_id, event_id)
        return _accepted(processed=False, reason="duplicate event", event_id=event_id)

    # ---- 7 + 8. Group or create ------------------------------------------ #
    try:
        result = await run_in_threadpool(_group_or_create, user_id, event, payload)
    except DatabaseError:
        if event_id:
            await run_in_threadpool(redis_svc.release, f"event:{user_id}:{event_id}")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Temporarily unavailable.")

    if result.get("grouped"):
        return _accepted(processed=True, grouped=True, incident_id=result["incident_id"], event_id=event_id)

    incident_id = result["incident_id"]
    task_id = await run_in_threadpool(_enqueue, incident_id)
    logger.info(
        "Webhook: accepted | user_id=%s | incident_id=%s | event_id=%s | queued=%s", user_id, incident_id, event_id, bool(task_id)
    )
    return _accepted(processed=True, incident_id=incident_id, event_id=event_id, queued=bool(task_id))


# ================================================================== #
# Helpers                                                              #
# ================================================================== #

async def _read_body(request: Request) -> bytes:
    limit = settings.WEBHOOK_MAX_BODY_BYTES
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(413, "Payload too large.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(413, "Payload too large.")
    if not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty request body.")
    return bytes(body)


def _signature_valid(body: bytes, header: Optional[str], secret: str) -> bool:
    if not header:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.strip().lower())


def _group_or_create(user_id: str, event: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    fingerprint = event["fingerprint"]
    seen_at = db.utcnow()
    with redis_svc.lock(f"group:{user_id}:{fingerprint}"):
        existing = db.find_active_incident_by_fingerprint(user_id, fingerprint, settings.INCIDENT_GROUPING_WINDOW_HOURS)
        if existing:
            count = db.record_occurrence(existing["id"], user_id, seen_at)
            logger.info("Webhook: grouped repeat | incident_id=%s | occurrences=%d", existing["id"], count)
            return {"grouped": True, "incident_id": existing["id"]}

        incident_id = str(uuid.uuid4())
        db.create_incident(
            {
                "id": incident_id,
                "user_id": user_id,
                "sentry_event_id": event.get("event_id"),
                "fingerprint": fingerprint,
                "error_type": event.get("error_type"),
                "error_message": event.get("error_message"),
                "culprit": event.get("culprit"),
                "environment": event.get("environment"),
                "level": event.get("level"),
                "platform": event.get("platform"),
                "sentry_project": event.get("project"),
                "sentry_issue_id": event.get("issue_id"),
                "sentry_issue_url": event.get("issue_url"),
                "stack_trace": frames_for_storage(event.get("frames") or []),
                "raw_payload": payload_for_storage(payload),
                "status": "queued",
                "current_step": "Queued",
                "occurrence_count": 1,
                "last_seen_at": seen_at,
                "analysis_run": 1,
                "attempts": 0,
            }
        )
        return {"grouped": False, "incident_id": incident_id}


def _enqueue(incident_id: str) -> Optional[str]:
    try:
        from app.workers.tasks import process_incident

        return process_incident.delay(incident_id).id
    except Exception as exc:
        # The incident is stored as "queued"; recover_stale_incidents re-enqueues it.
        logger.error("Webhook: enqueue failed (will be recovered) | incident_id=%s | error=%s", incident_id, exc)
        return None


def _accepted(**content: Any) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"accepted": True, **content})
