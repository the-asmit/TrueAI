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
When SENTRY_WEBHOOK_SECRET is configured, the endpoint verifies the
sentry-hook-signature header (HMAC-SHA256 of the raw body keyed on the
webhook secret) before processing the payload.  This prevents replay attacks
and spoofed webhooks.  Verification is skipped gracefully (with a WARNING
log) when the secret is not configured, so development environments work
without additional setup.

If the signature header is present but does not match → HTTP 401.
If the header is absent and no secret is configured → request proceeds.

Rate limiting
─────────────
Each API key (?key=) is rate-limited to RATE_LIMIT_PER_MINUTE requests per
minute via slowapi.  Anonymous callers (no key) share a single "anonymous"
bucket.  Exceeded limits return HTTP 429.

Processing flow
───────────────
1. Authenticate request (API key → user_id).
2. Optionally verify Sentry signature.
3. Parse raw body against SentryWebhookPayload schema (defensive).
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
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.dependencies import get_webhook_user
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.webhook import SentryWebhookPayload

logger = get_logger(__name__)

router = APIRouter()


# ================================================================== #
# Rate-limiter key — full API key from query param                    #
# ================================================================== #

def _webhook_key_func(request: Request) -> str:
    """
    Derive the rate-limiter bucket from the ?key= query parameter.

    Uses the full API key so each user has an independent quota.
    Falls back to 'anonymous' when no key is supplied (those requests
    will be rejected by the auth dependency anyway, but the limiter
    still tracks them).
    """
    return request.query_params.get("key") or "anonymous"


# Module-level limiter used by the @limiter.limit decorator below.
# SlowAPIMiddleware (attached in main.py) reads app.state.limiter; this
# local reference makes the decorator work without a circular import.
limiter = Limiter(key_func=_webhook_key_func)


# ================================================================== #
# Webhook endpoint                                                     #
# ================================================================== #

@router.post(
    "/sentry",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive Sentry webhook",
    response_description="Event accepted for asynchronous processing.",
)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
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

    # ---- Read raw body once (needed for HMAC verification) ---------- #
    raw_body: bytes = await request.body()

    # ---- Sentry signature verification ----------------------------- #
    _verify_sentry_signature(
        raw_body=raw_body,
        signature_header=sentry_hook_signature,
        request_id=request_id,
    )

    # ---- Parse payload from raw body ------------------------------- #
    # We use model_validate_json on the raw bytes so we do NOT call
    # request.json() separately (body stream already consumed above).
    try:
        parsed: Optional[SentryWebhookPayload] = (
            SentryWebhookPayload.model_validate_json(raw_body)
        )
        # Build a plain dict for downstream use (event_id lookup, Celery arg)
        payload_dict: Dict[str, Any] = parsed.model_dump()
    except ValidationError as exc:
        logger.warning(
            "Webhook: payload schema validation failed | request_id=%s | "
            "errors=%s",
            request_id,
            exc.error_count(),
        )
        # Don't fail hard — Sentry payloads vary; parse permissively
        import json as _json

        try:
            payload_dict = _json.loads(raw_body)
        except Exception:
            logger.warning(
                "Webhook: invalid JSON body | request_id=%s", request_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request body must be valid JSON.",
            )
        parsed = None
    except Exception:
        logger.warning(
            "Webhook: invalid JSON body | request_id=%s", request_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must be valid JSON.",
        )

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
    Verify the sentry-hook-signature header when SENTRY_WEBHOOK_SECRET is set.

    Sentry signs the raw request body with HMAC-SHA256 using the webhook
    secret configured in the integration settings.  We use
    hmac.compare_digest for constant-time comparison to prevent timing
    attacks.

    Behaviour matrix:
    ┌─────────────────────────┬──────────────────────┬─────────────┐
    │ SENTRY_WEBHOOK_SECRET   │ sentry-hook-signature│ Result      │
    ├─────────────────────────┼──────────────────────┼─────────────┤
    │ not set                 │ any / absent         │ skip (warn) │
    │ set                     │ absent               │ HTTP 401    │
    │ set                     │ present, matches     │ OK          │
    │ set                     │ present, mismatch    │ HTTP 401    │
    └─────────────────────────┴──────────────────────┴─────────────┘

    Raises:
        HTTPException(401) when verification fails.
    """

    secret: Optional[str] = settings.SENTRY_WEBHOOK_SECRET

    if not secret:
        # Fail-open: secret not configured → skip verification with a warning
        logger.warning(
            "Webhook: SENTRY_WEBHOOK_SECRET not configured | "
            "request_id=%s — skipping signature verification",
            request_id,
        )
        return

    # Secret is set — now we enforce the header
    if not signature_header:
        logger.warning(
            "Webhook: sentry-hook-signature header missing | request_id=%s",
            request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing webhook signature.",
        )

    try:
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
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Webhook signature verification failed.",
            )

        logger.debug(
            "Webhook: signature verified | request_id=%s", request_id
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Webhook: unexpected error during signature verification | "
            "request_id=%s | error=%s — rejecting request",
            request_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook signature verification error.",
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
