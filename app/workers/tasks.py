"""
Celery task definitions for TrueAI's async incident processing pipeline.

Task design principles
----------------------
1. Idempotency is ensured upstream by the Redis deduplication gate in the
   webhook route.  The task itself is not idempotent; do not call it twice
   for the same event without first removing the dedup key.

2. Exponential backoff is implemented explicitly:
       countdown = 30 ? (2 ^ self.request.retries)
   giving retry delays of 30 s ? 60 s ? 120 s.  This is intentional and
   must not be replaced by Celery's ``task_default_retry_delay``, which
   applies a fixed interval.

3. On maximum retries exceeded the task raises ``MaxRetriesExceededError``
   so Celery marks the task as FAILURE.  Result backends and monitoring
   tools (Flower, Sentry) will surface this correctly.

4. Supabase is updated to ``status="failed"`` only when the pipeline state
   contains an ``incident_id``.  If the pipeline crashed before the DB row
   was created, there is nothing to update and we skip silently ? never
   blindly attempt an update with a missing or fabricated ID.

5. Non-retriable terminal states:
   - ``status="failed"`` returned by the pipeline signals a permanent LLM
     logic error (bad request, auth failure, etc.).  Retrying cannot help
     and would waste quota.
   - ``status="duplicate"`` means the dedup gate already processed this
     event; retrying would create a duplicate incident row.
   In both cases the task returns the final_state immediately without
   scheduling a retry.

6. ``failure_reason`` is included in the final Supabase update when all
   retries are exhausted.  If the column does not exist in the schema the
   update will fail; ``_try_mark_incident_failed`` catches that error and
   logs it without masking the original exception.
"""

from __future__ import annotations

import asyncio
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from celery import Task
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded

from app.core.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

# Maximum number of retry attempts (must match celery_app.conf.task_max_retries
# so both the task decorator and the app-level default are consistent).
_MAX_RETRIES: int = 3

# Pipeline status values that indicate a permanent (non-transient) failure;
# retrying these would waste quota and potentially create duplicate records.
_NON_RETRIABLE_STATUSES: frozenset[str] = frozenset({"failed", "duplicate"})


# ------------------------------------------------------------------ #
# process_incident                                                     #
# ------------------------------------------------------------------ #

@celery_app.task(
    bind=True,
    name="trueai.tasks.process_incident",
    max_retries=_MAX_RETRIES,
    acks_late=True,          # redundant with global conf, but explicit is safer
    track_started=True,
)
def process_incident(self: Task, payload: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    Orchestrate the end-to-end incident analysis pipeline for a single Sentry event.

    Receives the raw Sentry webhook payload and the authenticated workspace
    user ID.  Delegates all AI/GitHub/Supabase work to
    :func:`~app.pipelines.incident_pipeline.run_incident_pipeline`, then
    handles retry logic and final failure recording here.

    Args:
        payload:  Raw Sentry webhook payload dict as received from the webhook
                  route (already validated by :class:`~app.schemas.webhook.SentryWebhookPayload`).
        user_id:  TrueAI workspace user identifier ? used for scoping
                  GitHub token lookups and Supabase row ownership.

    Returns:
        The final :class:`~app.core.state.IncidentState` dict on success.
        (Celery stores this in the result backend under the task ID.)

    Raises:
        :class:`celery.exceptions.Retry` on retriable failure.
        :class:`celery.exceptions.MaxRetriesExceededError` after all retries
        are exhausted, causing Celery to mark the task as FAILURE.
    """
    # ---- Context extraction ------------------------------------------- #
    task_id: str = self.request.id or "unknown"
    attempt: int = self.request.retries + 1         # 1-based for log readability
    max_attempts: int = _MAX_RETRIES + 1

    # Sentry event_id may live at different keys depending on SDK version.
    event_id: str = (
        payload.get("event_id")
        or payload.get("id")
        or "unknown"
    )

    logger.info(
        "process_incident START | task_id=%s | user_id=%s | event_id=%s | "
        "attempt=%s/%s",
        task_id,
        user_id,
        event_id,
        attempt,
        max_attempts,
    )

    # Mark task as STARTED so Flower / monitoring tools show real-time status.
    self.update_state(
        state="STARTED",
        meta={
            "task_id": task_id,
            "user_id": user_id,
            "event_id": event_id,
            "attempt": attempt,
        },
    )

    # ---- Pipeline execution ------------------------------------------- #

    # ``final_state`` is declared before the try block so the exception
    # handler can inspect it even when the pipeline partially populated it
    # (e.g. created the DB row) before raising.  If the pipeline raises
    # before returning, final_state remains None.
    final_state: Optional[Dict[str, Any]] = None

    try:
        # Lazy import to avoid circular dependencies at module load time and
        # to defer heavy imports (langchain, anthropic SDK) until the worker
        # process actually executes a task.
        from app.pipelines.incident_pipeline import run_incident_pipeline

        final_state = asyncio.run(run_incident_pipeline(payload=payload, user_id=user_id))

        # ---- Non-retriable terminal states check ---------------------- #
        # The pipeline contract (see incident_pipeline.py) guarantees it
        # never raises ? it returns a dict with status="failed" when a
        # permanent LLM error occurs.  We must inspect the returned status
        # before deciding whether to retry, because blindly retrying a
        # bad-request or auth error burns quota without any hope of success.
        pipeline_status: str = (final_state or {}).get("status", "unknown")
        incident_id: Optional[str] = (final_state or {}).get("incident_id")

        if pipeline_status in _NON_RETRIABLE_STATUSES:
            logger.warning(
                "process_incident NON_RETRIABLE | task_id=%s | user_id=%s | "
                "event_id=%s | incident_id=%s | pipeline_status=%s | "
                "attempt=%s/%s ? returning without retry.",
                task_id,
                user_id,
                event_id,
                incident_id or "n/a",
                pipeline_status,
                attempt,
                max_attempts,
            )
            # Return the state as-is; Celery marks the task SUCCESS (which is
            # accurate ? the task ran to completion; the pipeline determined
            # no fix was possible).
            return final_state or {}

        # ---- Success path --------------------------------------------- #
        logger.info(
            "process_incident SUCCESS | task_id=%s | user_id=%s | event_id=%s | "
            "incident_id=%s | pipeline_status=%s | attempt=%s/%s",
            task_id,
            user_id,
            event_id,
            incident_id or "n/a",
            pipeline_status,
            attempt,
            max_attempts,
        )

        return final_state or {}

    # ---- Soft time limit (10 min) ------------------------------------- #
    except SoftTimeLimitExceeded as exc:
        _handle_task_failure(
            exc=exc,
            label="SOFT_TIME_LIMIT_EXCEEDED",
            task_id=task_id,
            user_id=user_id,
            event_id=event_id,
            attempt=attempt,
            max_attempts=max_attempts,
            final_state=final_state,
            include_traceback=False,  # no traceback ? it's a signal, not a bug
        )
        _schedule_retry_or_give_up(
            self=self,
            exc=exc,
            task_id=task_id,
            user_id=user_id,
            event_id=event_id,
            final_state=final_state,
        )

    # ---- All other failures ------------------------------------------- #
    except Exception as exc:
        _handle_task_failure(
            exc=exc,
            label="FAILED",
            task_id=task_id,
            user_id=user_id,
            event_id=event_id,
            attempt=attempt,
            max_attempts=max_attempts,
            final_state=final_state,
            include_traceback=True,
        )
        _schedule_retry_or_give_up(
            self=self,
            exc=exc,
            task_id=task_id,
            user_id=user_id,
            event_id=event_id,
            final_state=final_state,
        )


# ------------------------------------------------------------------ #
# health_check                                                         #
# ------------------------------------------------------------------ #

@celery_app.task(
    name="trueai.tasks.health_check",
    max_retries=0,
    ignore_result=False,
)
def health_check() -> Dict[str, Any]:
    """
    Lightweight liveness probe for the Celery worker.

    Can be invoked by monitoring infrastructure (Kubernetes probes, Flower,
    custom dashboards) to confirm the worker is alive and accepting tasks.

    Returns:
        Dict with ``status`` and current UTC ``timestamp``.
    """
    now = datetime.now(tz=timezone.utc)
    result = {
        "status": "ok",
        "timestamp": now.isoformat(),
        "worker": "celery",
    }
    logger.debug("health_check | timestamp=%s", now.isoformat())
    return result


# ------------------------------------------------------------------ #
# Internal helpers                                                     #
# ------------------------------------------------------------------ #

def _schedule_retry_or_give_up(
    self: Task,
    exc: Exception,
    task_id: str,
    user_id: str,
    event_id: str,
    final_state: Optional[Dict[str, Any]],
) -> None:
    """
    Attempt to schedule a retry with true exponential backoff, or raise
    :class:`~celery.exceptions.MaxRetriesExceededError` when all retries
    are consumed.

    Backoff schedule:
        Attempt 1 fails ? retry in  30 s  (30 ? 2?)
        Attempt 2 fails ? retry in  60 s  (30 ? 2?)
        Attempt 3 fails ? retry in 120 s  (30 ? 2?)
        Attempt 4 fails ? MaxRetriesExceededError (task marked FAILURE)

    On MaxRetriesExceededError the incident row is updated to
    ``status="failed"`` with a ``failure_reason`` if the column exists.

    Args:
        self:        Bound Celery task instance.
        exc:         The exception that caused the failure.
        task_id:     Task UUID for structured log context.
        user_id:     Workspace user identifier for structured log context.
        event_id:    Sentry event ID for structured log context.
        final_state: Pipeline state dict if available (used to extract
                     ``incident_id`` for the final Supabase update).

    Raises:
        :class:`celery.exceptions.Retry`               ? if a retry was scheduled.
        :class:`celery.exceptions.MaxRetriesExceededError` ? after last attempt.
    """
    countdown: int = 30 * (2 ** self.request.retries)

    logger.info(
        "process_incident RETRY_SCHEDULED | task_id=%s | user_id=%s | "
        "event_id=%s | retry=%s/%s | countdown=%ds",
        task_id,
        user_id,
        event_id,
        self.request.retries + 1,
        _MAX_RETRIES,
        countdown,
    )

    try:
        # self.retry() raises celery.exceptions.Retry; that exception must
        # propagate up to Celery's task runner.  We re-raise it explicitly
        # so it is never accidentally swallowed by a caller's except block.
        raise self.retry(exc=exc, countdown=countdown)

    except MaxRetriesExceededError:
        logger.error(
            "process_incident MAX_RETRIES_EXCEEDED | task_id=%s | user_id=%s | "
            "event_id=%s | retries_attempted=%d | giving_up=True",
            task_id,
            user_id,
            event_id,
            _MAX_RETRIES,
        )

        # On exhaustion, persist a failure_reason so on-call engineers can
        # diagnose why the task gave up without trawling worker logs.
        incident_id: Optional[str] = (final_state or {}).get("incident_id")
        if incident_id:
            failure_reason: str = (
                f"Task exhausted {_MAX_RETRIES} retries. "
                f"Last error: {type(exc).__name__}: {exc}"
            )
            _try_mark_incident_failed(
                incident_id=incident_id,
                error_message=failure_reason,
                task_id=task_id,
                include_failure_reason=True,
            )
        else:
            logger.debug(
                "process_incident MAX_RETRIES_EXCEEDED | task_id=%s | "
                "skipping Supabase update ? no incident_id in pipeline state.",
                task_id,
            )

        # Re-raise so Celery marks the task as FAILURE in the result backend.
        raise


def _handle_task_failure(
    exc: Exception,
    label: str,
    task_id: str,
    user_id: str,
    event_id: str,
    attempt: int,
    max_attempts: int,
    final_state: Optional[Dict[str, Any]],
    include_traceback: bool = True,
) -> None:
    """
    Log the failure and conditionally update the incident row to ``failed``.

    Supabase is only written to when ``final_state`` contains a non-empty
    ``incident_id``.  This guards against a race where the pipeline crashed
    before the DB row was created ? attempting an update with a missing ID
    would silently update zero rows or, worse, match an unrelated row.

    Args:
        exc:               The exception that caused the failure.
        label:             Log label (e.g. ``"FAILED"`` or
                           ``"SOFT_TIME_LIMIT_EXCEEDED"``).
        task_id:           Celery task UUID.
        user_id:           Workspace user identifier.
        event_id:          Sentry event UUID.
        attempt:           1-based attempt number.
        max_attempts:      Total allowed attempts (retries + 1).
        final_state:       Pipeline state dict if available; ``None`` if the
                           pipeline raised before returning.
        include_traceback: Whether to log the full traceback (False for
                           signal-based limits which have no useful traceback).
    """
    tb = traceback.format_exc() if include_traceback else "(no traceback)"

    logger.error(
        "process_incident %s | task_id=%s | user_id=%s | event_id=%s | "
        "attempt=%s/%s | error_type=%s | error=%s\n%s",
        label,
        task_id,
        user_id,
        event_id,
        attempt,
        max_attempts,
        type(exc).__name__,
        exc,
        tb,
    )

    # Update the incident row if ? and only if ? we know its ID.
    incident_id: Optional[str] = (final_state or {}).get("incident_id")
    if incident_id:
        _try_mark_incident_failed(
            incident_id=incident_id,
            error_message=f"{type(exc).__name__}: {exc}",
            task_id=task_id,
            include_failure_reason=False,  # intermediate attempts: status only
        )
    else:
        logger.debug(
            "process_incident %s | task_id=%s | skipping Supabase update ? "
            "no incident_id in pipeline state.",
            label,
            task_id,
        )


def _try_mark_incident_failed(
    incident_id: str,
    error_message: str,
    task_id: str,
    include_failure_reason: bool = False,
) -> None:
    """
    Update the incident's status to ``failed`` in Supabase.

    When *include_failure_reason* is True (used only on final retry
    exhaustion) the error message is also written to the ``error_message``
    column so on-call engineers can diagnose the failure without grepping logs.

    Wrapped in its own try/except so that a secondary Supabase failure
    never masks the original pipeline exception or disrupts retry logic.

    Args:
        incident_id:            UUID of the incident row to update.
        error_message:          Human-readable description of what went wrong.
        task_id:                Celery task UUID (for log context only).
        include_failure_reason: If True, also write the error_message column.
    """
    try:
        from app.services.supabase import update_incident

        update_data: Dict[str, Any] = {"status": "failed"}
        if include_failure_reason:
            # Truncate to 1 000 characters to stay well within typical text
            # column limits; the full error is always available in worker logs.
            # Note: writes to the existing `error_message` column — not a
            # separate `failure_reason` column (which is not in the schema).
            update_data["error_message"] = error_message[:1_000]

        update_incident(
            incident_id=incident_id,
            update_data=update_data,
        )
        logger.debug(
            "_try_mark_incident_failed: incident_id=%s marked as failed "
            "(include_failure_reason=%s) | task_id=%s.",
            incident_id,
            include_failure_reason,
            task_id,
        )

    except Exception as supabase_exc:
        # Log at ERROR so this is visible, but do not re-raise — the original
        # pipeline exception takes priority.
        logger.error(
            "_try_mark_incident_failed: Supabase update failed for incident_id=%s | "
            "task_id=%s | supabase_error=%s — %s.",
            incident_id,
            task_id,
            type(supabase_exc).__name__,
            supabase_exc,
        )

