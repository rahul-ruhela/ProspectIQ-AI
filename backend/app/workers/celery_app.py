"""Celery application: queues, retries, routing and periodic maintenance."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

celery_app = Celery(
    "prospectiq",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    result_expires=60 * 60 * 24 * 3,
    # A full research job is long-running; kill it well before it can wedge a worker.
    task_soft_time_limit=60 * 55,
    task_time_limit=60 * 60,
    task_default_queue="default",
    task_routes={
        "research.run_job": {"queue": "research"},
        "research.rescore_company": {"queue": "enrichment"},
        "maintenance.*": {"queue": "default"},
    },
    beat_schedule={
        "roll-up-daily-costs": {
            "task": "maintenance.rollup_costs",
            "schedule": crontab(hour=1, minute=0),
        },
        "expire-stale-memory": {
            "task": "maintenance.expire_memory",
            "schedule": crontab(hour=2, minute=0),
        },
        "reap-stuck-jobs": {
            "task": "maintenance.reap_stuck_jobs",
            "schedule": crontab(minute="*/15"),
        },
    },
)
