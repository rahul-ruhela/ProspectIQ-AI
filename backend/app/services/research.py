"""Research job lifecycle: dispatch to Celery, or run inline for local development."""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.agents.base import AgentContext
from app.agents.orchestrator import CEOOrchestratorAgent
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.campaign import ResearchJob
from app.models.enums import JobStatus

logger = get_logger(__name__)


def dispatch_job(
    db: Session,
    job: ResearchJob,
    *,
    max_companies: int | None = None,
    run_inline: bool = False,
) -> None:
    """Hand a queued job to the workers, falling back to inline execution."""
    if run_inline:
        run_research_job(job.id, max_companies=max_companies)
        return

    try:
        from app.workers.tasks import run_research_job_task

        async_result = run_research_job_task.delay(str(job.id), max_companies)
        job.celery_task_id = async_result.id
        db.commit()
        logger.info("job_dispatched", job_id=str(job.id), task_id=async_result.id)
    except Exception as exc:
        # A broker outage must not silently swallow the user's click.
        logger.warning("celery_dispatch_failed", job_id=str(job.id), error=str(exc))
        job.status = JobStatus.FAILED
        job.error = (
            "Could not reach the background worker queue. Start Redis and the Celery "
            f"worker, or retry with run_inline=true. ({type(exc).__name__})"
        )
        job.finished_at = datetime.now(UTC)
        db.commit()


def run_research_job(job_id: uuid.UUID | str, *, max_companies: int | None = None) -> dict:
    """Execute one research job end to end. Safe to call from a worker or inline."""
    job_uuid = job_id if isinstance(job_id, uuid.UUID) else uuid.UUID(str(job_id))

    with session_scope() as db:
        job = db.get(ResearchJob, job_uuid)
        if job is None:
            return {"ok": False, "error": "job_not_found"}
        if job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
            return {"ok": False, "error": f"job_already_{job.status}"}

        ctx = AgentContext(
            db=db,
            organization_id=job.organization_id,
            research_job_id=job.id,
            campaign_id=job.campaign_id,
        )
        orchestrator = CEOOrchestratorAgent()
        try:
            result = asyncio.run(
                orchestrator.execute(
                    ctx, {"research_job_id": str(job.id), "max_companies": max_companies}
                )
            )
        except Exception as exc:
            logger.exception("research_job_crashed", job_id=str(job_uuid))
            db.rollback()
            job = db.get(ResearchJob, job_uuid)
            if job is not None:
                job.status = JobStatus.FAILED
                job.error = f"{type(exc).__name__}: {exc}"[:2000]
                job.finished_at = datetime.now(UTC)
            return {"ok": False, "error": str(exc)}

        return {"ok": result.ok, "data": result.data, "error": result.error}
