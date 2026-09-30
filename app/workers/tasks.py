"""
Celery tasks for TrueAI.

process_incident(incident_id)
    Runs the multi-agent pipeline for one incident.  Only the incident id
    travels through the broker — the payload lives on the incident row — so
    retries and re-analysis always update the same incident.

    Retry policy: a failure the pipeline marks ``error_retryable`` (provider
    outage, GitHub/database hiccup, timeout) is retried with exponential
    backoff (30 s → 60 s → 120 s); the incident shows "queued" meanwhile.
    Permanent failures (bad credentials, unparseable payload) are recorded
    once and never retried.  The task returns a compact summary — never the
    full pipeline state, which contains source code.

sync_pull_requests()             every 10 min (beat): PR merge tracking
recover_stale_incidents()        every 5 min (beat): re-queue lost work
health_check()                   liveness probe for monitoring
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Dict

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.core.logging import get_logger
from app.services import redis as redis_svc
from app.services import supabase as db
from app.workers import async_runner
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

MAX_RETRIES = 3


@celery_app.task(bind=True, name="trueai.tasks.process_incident", max_retries=MAX_RETRIES, acks_late=True)
def process_incident(self: Task, incident_id: str) -> Dict[str, Any]:
    from app.pipelines.incident_pipeline import run_incident_pipeline

    attempt = self.request.retries + 1
    logger.info("process_incident START | incident_id=%s | attempt=%d/%d", incident_id, attempt, MAX_RETRIES + 1)

    # Only one worker may analyse an incident at a time (duplicate deliveries,
    # recovery re-queues).  Redis being down must not stop processing.
    lock_name = f"processing:{incident_id}"
    if redis_svc.claim_once(lock_name, settings.PIPELINE_TIMEOUT_SECONDS + 300) is False:
        logger.info("process_incident SKIP | incident_id=%s | already being processed", incident_id)
        return {"incident_id": incident_id, "status": "skipped"}

    try:
        result = async_runner.run(run_incident_pipeline(incident_id))
    except SoftTimeLimitExceeded:
        message = "The analysis exceeded the worker time limit."
        _mark_failed(incident_id, message)
        result = {"incident_id": incident_id, "status": "failed", "error": message, "error_retryable": True}
    finally:
        redis_svc.release(lock_name)

    status = result.get("status")
    if status == "failed" and result.get("error_retryable") and self.request.retries < MAX_RETRIES:
        countdown = int(30 * (2 ** self.request.retries) + random.uniform(0, 10))
        _set_queued_for_retry(incident_id, countdown, result.get("error") or "transient error")
        logger.warning(
            "process_incident RETRY | incident_id=%s | in=%ds | error=%s", incident_id, countdown, result.get("error")
        )
        raise self.retry(countdown=countdown)

    summary = {
        "incident_id": incident_id,
        "status": status,
        "error": result.get("error"),
        "pr_url": (result.get("pr") or {}).get("url"),
    }
    logger.info("process_incident END | incident_id=%s | status=%s", incident_id, status)
    return summary


@celery_app.task(name="trueai.tasks.sync_pull_requests")
def sync_pull_requests() -> Dict[str, int]:
    from app.services.pr_sync import sync_all_open

    if redis_svc.claim_once("task:sync_pull_requests", 300) is False:
        return {"skipped": 1}
    try:
        counts = sync_all_open()
    finally:
        redis_svc.release("task:sync_pull_requests")
    logger.info("sync_pull_requests | %s", counts)
    return counts


@celery_app.task(name="trueai.tasks.recover_stale_incidents")
def recover_stale_incidents() -> Dict[str, int]:
    """
    Safety net for lost work:
      - queued for 15+ minutes (enqueue lost, broker flushed) → enqueue again
      - processing past the time limit (worker killed) → re-queue, or fail
        after 3 attempts
    """
    requeued = failed = 0
    for row in db.list_stale_incidents("queued", older_than_minutes=15):
        if redis_svc.claim_once(f"requeue:{row['id']}", 900) is not False:
            process_incident.delay(row["id"])
            requeued += 1

    stuck_after = (settings.PIPELINE_TIMEOUT_SECONDS + 180) // 60 + 5
    for row in db.list_stale_incidents("processing", older_than_minutes=stuck_after):
        if int(row.get("attempts") or 0) >= MAX_RETRIES + 1:
            _mark_failed(row["id"], "The analysis was interrupted repeatedly (worker restarted). Use Re-run to try again.")
            failed += 1
        elif redis_svc.claim_once(f"requeue:{row['id']}", 900) is not False:
            db.update_incident(row["id"], {"status": "queued", "current_step": "Re-queued after an interrupted run"})
            process_incident.delay(row["id"])
            requeued += 1
    if requeued or failed:
        logger.warning("recover_stale_incidents | requeued=%d | failed=%d", requeued, failed)
    return {"requeued": requeued, "failed": failed}


@celery_app.task(name="trueai.tasks.health_check")
def health_check() -> Dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now(tz=timezone.utc).isoformat()}


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _mark_failed(incident_id: str, message: str) -> None:
    try:
        db.update_incident(
            incident_id,
            {"status": "failed", "pipeline_error": message[:1000], "current_step": None, "completed_at": db.utcnow()},
        )
    except Exception as exc:
        logger.error("Could not mark incident failed | incident_id=%s | error=%s", incident_id, exc)


def _set_queued_for_retry(incident_id: str, countdown: int, reason: str) -> None:
    try:
        db.update_incident(
            incident_id,
            {"status": "queued", "current_step": f"Retrying in {countdown}s — {reason[:200]}", "pipeline_error": None},
        )
    except Exception as exc:
        logger.error("Could not mark incident queued | incident_id=%s | error=%s", incident_id, exc)
