"""
Celery application for TrueAI's background work.

Run the worker (add ``--pool=solo`` on Windows):
    celery -A app.workers.celery_app worker --loglevel=info

Run the scheduler for PR merge tracking and stuck-incident recovery:
    celery -A app.workers.celery_app beat --loglevel=info

Reliability settings
────────────────────
- JSON serialisation only (no pickle → no deserialisation attacks via the broker).
- ``task_acks_late`` + ``task_reject_on_worker_lost``: a task is removed from
  the queue only after it finishes; a crashed worker's task is redelivered.
- ``worker_prefetch_multiplier=1``: one long AI task never blocks others.
- Soft/hard time limits sit above PIPELINE_TIMEOUT_SECONDS so the pipeline
  normally times out gracefully first.
- The broker visibility timeout exceeds the hard limit so a running task is
  never redelivered to a second worker.
"""

from app.core.logging import configure_logging

configure_logging("worker")

from celery import Celery  # noqa: E402
from celery.schedules import crontab  # noqa: E402
from celery.signals import worker_ready  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.logging import get_logger  # noqa: E402

logger = get_logger(__name__)

celery_app = Celery(
    "trueai",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

_SOFT_LIMIT = settings.PIPELINE_TIMEOUT_SECONDS + 60
_HARD_LIMIT = _SOFT_LIMIT + 60

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=_SOFT_LIMIT,
    task_time_limit=_HARD_LIMIT,
    worker_max_tasks_per_child=200,
    result_expires=86_400,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    broker_transport_options={"visibility_timeout": _HARD_LIMIT * 3},
    # Publishing from the API must fail fast when Redis is down (the webhook
    # stores the incident first and the recovery task re-enqueues it).
    task_publish_retry=True,
    task_publish_retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.5, "interval_max": 1},
    timezone="UTC",
    enable_utc=True,
    worker_hijack_root_logger=False,
    beat_schedule={
        "sync-open-pull-requests": {
            "task": "trueai.tasks.sync_pull_requests",
            "schedule": crontab(minute="*/10"),
        },
        "recover-stale-incidents": {
            "task": "trueai.tasks.recover_stale_incidents",
            "schedule": crontab(minute="*/5"),
        },
    },
)


@worker_ready.connect
def on_worker_ready(sender, **kwargs) -> None:  # noqa: ANN001
    try:
        from app.core.llm import check_models_available, configured_agents, validate_llm_configuration

        validate_llm_configuration()
        for agent, model in configured_agents().items():
            logger.info("Agent %-13s -> %s", agent, model)
        for warning in check_models_available():
            logger.error("LLM model check: %s", warning)
    except Exception as exc:
        logger.error("LLM configuration problem: %s", exc)
    logger.info("Celery worker ready.")
