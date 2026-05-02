"""
Celery application factory and configuration for TrueAI.

Architecture notes
------------------
- Broker and result backend both point at Redis (configured via environment).
- ``task_acks_late=True`` + ``worker_prefetch_multiplier=1`` is the correct
  combination for reliability:  the task is removed from the queue only after
  it finishes, and the worker pulls exactly one task at a time.  This prevents
  task loss when a worker process is killed mid-execution and avoids one slow
  AI pipeline starving other workers.
- ``task_serializer="json"`` enforces that all task arguments are plain
  JSON-serialisable types.  We deliberately avoid pickle to prevent
  deserialization-based code execution attacks if the Redis broker is ever
  compromised.
- Time limits are set at the application level as safety rails:
    soft (10 min) ? SIGTERM sent to the task, allowing graceful cleanup.
    hard (12 min) ? SIGKILL; worker process is replaced by a new one.
  The AI pipeline (Claude + GitHub + Supabase) typically completes in < 90 s
  under normal load; these limits protect against runaway tasks without
  impacting normal operation.
- ``worker_max_tasks_per_child=500`` recycles worker processes periodically
  to prevent memory creep from long-lived Python processes.
"""

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------ #
# Application instance                                                 #
# ------------------------------------------------------------------ #

celery_app = Celery(
    "trueai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks",   # auto-discover tasks on worker startup
    ],
)

# ------------------------------------------------------------------ #
# Configuration                                                        #
# ------------------------------------------------------------------ #

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Reliability
    task_track_started=True,           # transitions task to STARTED state immediately
    task_acks_late=True,               # ack only after task completes, not on receipt
    task_reject_on_worker_lost=True,   # requeue if worker process dies mid-task
    worker_prefetch_multiplier=1,      # pull one task at a time per worker thread

    # Retry defaults (individual tasks override countdown for exponential backoff)
    task_max_retries=3,
    task_default_retry_delay=30,       # seconds; base for 30 ? 2^n exponential formula

    # Safety limits (prevent runaway AI calls from blocking workers indefinitely)
    task_soft_time_limit=600,      # 10 min ? SoftTimeLimitExceeded raised in task
    task_time_limit=720,           # 12 min ? SIGKILL + worker restart

    # Memory hygiene
    worker_max_tasks_per_child=500,

    # Result storage
    result_expires=86_400,         # keep results for 24 hours then auto-expire

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Logging: let our structured logger handle output; suppress Celery's default
    # hijacking of the root logger format.
    worker_hijack_root_logger=False,
    worker_log_format="%(message)s",
    worker_task_log_format="%(message)s",
)

# ------------------------------------------------------------------ #
# Worker lifecycle signals                                             #
# ------------------------------------------------------------------ #

@worker_ready.connect
def on_worker_ready(sender, **kwargs) -> None:
    logger.info(
        "Celery worker ready | app=%s | broker=%s.",
        celery_app.main,
        _mask_url(settings.CELERY_BROKER_URL),
    )


@worker_shutdown.connect
def on_worker_shutdown(sender, **kwargs) -> None:
    logger.info("Celery worker shutting down | app=%s.", celery_app.main)


# ------------------------------------------------------------------ #
# Internal helpers                                                     #
# ------------------------------------------------------------------ #

def _mask_url(url: str) -> str:
    """Redact credentials from a broker URL for safe logging."""
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        if parsed.password:
            safe = parsed._replace(
                netloc=parsed.netloc.replace(f":{parsed.password}", ":****")
            )
            return urlunparse(safe)
    except Exception:
        pass
    return url
