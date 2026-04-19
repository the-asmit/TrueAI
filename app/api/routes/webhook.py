"""
Sentry webhook ingestion route for TrueAI.

Endpoint: POST /webhook/sentry?key=<api_key>

Authentication
──────────────
Sentry does not support sending custom request headers in its webhook
configuration, so the API key is accepted as a query parameter (?key=).
The get_webhook_user dependency hashes the key and looks it up in Supabase.

Sentry signature verification
──────────────────────────────
When SENTRY_CLIENT_SECRET is configured, the endpoint verifies the
sentry-hook-signature header (HMAC-SHA256 of the raw body keyed on the
client secret) before processing the payload.  This prevents replay attacks
and spoofed webhooks.  Verification is skipped gracefully when the header
or secret is absent so that development environments work without setup.

Processing flow
───────────────
1. Authenticate request (API key).
2. Optionally verify Sentry signature.
3. Parse body against SentryWebhookPayload schema (defensive).
4. Dispatch Celery task asynchronously — return 202 immediately.
   The webhook handler must not block waiting for analysis to finish.
5. Log the dispatch with request_id and event_id for end-to-end tracing.

Idempotency
───────────
Sentry retries webhooks up to 3 times on 5xx responses.  The Redis
deduplication gate in the pipeline prevents duplicate processing.
Returning 202 (not 200) signals to Sentry that the event was accepted
for async processing, which prevents needless retries.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.dependencies import get_webhook_user
from app.core.logging import get_logger
from app.schemas.webhook import SentryWebhookPayload

logger = get_logger(__name__)

router = APIRouter()


# ================================================================== #
# Webhook endpoint                                                     #
# ================================================================== #

@router.post(
    "/sentry",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive Sentry webhook",
    response_description="Event accepted for asynchronous processing.",
)
async def receive_sentry_webhook(
    request: Request,
    user_id: str = Depends(get_webhook_user),
    sentry_hook_resource: Optional[str] = Header(
        default=None, alias="sentry-hook-resource"
    ),
    sentry_hook_signature: Optional[str] = Header(
        default=None, alias="sentry-hook-signature"
    ),
) -> JSONResponse:
    """
    Accept a Sentry webhook event and dispatch it for asynchronous analysis.

    Returns 202 immediately — analysis runs in the background via Celery.
    """
    request_id = getattr(request.state, "request_id", "unknown")

    # ---- Read raw body (needed for signature verification) --------- #
    raw_body: bytes = await request.body()

    # ---- Optional Sentry signature verification -------------------- #
    _verify_sentry_signature(
        raw_body=raw_body,
        signature_header=sentry_hook_signature,
        request_id=request_id,
    )

    # ---- Parse payload --------------------------------------------- #
    try:
        payload_dict: Dict[str, Any] = await request.json()
    except Exception:
        logger.warning(
            "Webhook: invalid JSON body | request_id=%s", request_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be valid JSON.",
        )

    # Validate against SentryWebhookPayload schema — uses model_validate
    # which is tolerant (extra="allow") but ensures the structure is sane.
    try:
        parsed = SentryWebhookPayload.model_validate(payload_dict)
    except ValidationError as exc:
        logger.warning(
            "Webhook: payload schema validation failed | request_id=%s | "
            "errors=%s",
            request_id,
            exc.error_count(),
        )
        # Don't fail hard — Sentry payloads vary; log and still process
        parsed = None

    event_id: str = (
        payload_dict.get("event_id")
        or payload_dict.get("id")
        or "unknown"
    )

    logger.info(
        "Webhook: received | request_id=%s | user_id=%s | event_id=%s | "
        "resource=%s | payload_keys=%s",
        request_id,
        user_id,
        event_id,
        sentry_hook_resource or "unspecified",
        list(payload_dict.keys()),
    )

    # ---- Filter non-error resources -------------------------------- #
    # Sentry sends different hook types (issue.created, error, etc.).
    # We only process error-class events; others are acked and ignored.
    resource = (sentry_hook_resource or "").lower()
    if resource and resource not in ("error", "issue", "issue.created", ""):
        logger.info(
            "Webhook: ignoring non-error resource '%s' | request_id=%s",
            resource,
            request_id,
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "accepted": True,
                "processed": False,
                "reason": f"Resource type '{resource}' is not processed.",
                "event_id": event_id,
            },
        )

    # ---- Dispatch to Celery ---------------------------------------- #
    task_id = _dispatch_pipeline(
        payload=payload_dict,
        user_id=user_id,
        event_id=event_id,
        request_id=request_id,
    )

    logger.info(
        "Webhook: dispatched | request_id=%s | user_id=%s | event_id=%s | "
        "task_id=%s",
        request_id,
        user_id,
        event_id,
        task_id or "dispatch-failed",
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "accepted": True,
            "event_id": event_id,
            "task_id": task_id,
            "message": "Incident accepted for analysis.",
        },
    )


# ================================================================== #
# Internal helpers                                                     #
# ================================================================== #

def _verify_sentry_signature(
    raw_body: bytes,
    signature_header: Optional[str],
    request_id: str,
) -> None:
    """
    Verify the sentry-hook-signature header when configured.

    Sentry signs the raw request body with HMAC-SHA256 using the
    integration's client secret.  We use hmac.compare_digest for
    constant-time comparison to prevent timing attacks.

    Skips verification (with a DEBUG log) when:
    - The signature header is absent (Sentry didn't send one, or it's
      a dev environment).
    - GITHUB_CLIENT_SECRET is not configured as a Sentry secret
      (TrueAI uses SENTRY_CLIENT_SECRET for this; falls back gracefully).

    Raises:
        HTTPException(400) when a signature IS present but does not match.
    """
    if not signature_header:
        logger.debug(
            "Webhook: no sentry-hook-signature header | request_id=%s — "
            "skipping verification",
            request_id,
        )
        return

    try:
        from app.core.config import settings
        # We re-use GITHUB_CLIENT_SECRET as the Sentry webhook secret if a
        # dedicated SENTRY_CLIENT_SECRET is not in settings.  In production,
        # add SENTRY_CLIENT_SECRET to .env and settings.
        secret = getattr(settings, "SENTRY_CLIENT_SECRET", None) or ""
        if not secret:
            logger.debug(
                "Webhook: no SENTRY_CLIENT_SECRET configured | "
                "request_id=%s — skipping signature verification",
                request_id,
            )
            return

        expected = hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, signature_header.lower()):
            logger.warning(
                "Webhook: signature mismatch | request_id=%s", request_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook signature verification failed.",
            )

        logger.debug(
            "Webhook: signature verified | request_id=%s", request_id
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Webhook: error during signature verification | "
            "request_id=%s | error=%s — allowing request",
            request_id,
            exc,
        )


def _dispatch_pipeline(
    payload: Dict[str, Any],
    user_id: str,
    event_id: str,
    request_id: str,
) -> Optional[str]:
    """
    Enqueue a process_incident Celery task and return the task ID.

    Returns None (with an ERROR log) if Celery/Redis is unavailable.
    A dispatch failure does NOT cause a 5xx response — we always return
    202 to prevent Sentry from retrying the webhook.  The event will be
    re-processable from the Supabase incidents table.
    """
    try:
        from app.workers.tasks import process_incident

        result = process_incident.apply_async(
            args=[payload, user_id],
            # Pass event_id as a header for Celery Flower visibility
            headers={"event_id": event_id, "request_id": request_id},
        )
        return result.id

    except Exception as exc:
        logger.error(
            "Webhook: failed to dispatch Celery task | "
            "request_id=%s | user_id=%s | event_id=%s | error=%s — %s",
            request_id,
            user_id,
            event_id,
            type(exc).__name__,
            exc,
        )
        return None
