"""Background tasks: research execution, re-scoring and scheduled maintenance."""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from celery import shared_task
from sqlalchemy import func, select

from app.agents.base import AgentContext
from app.agents.quality import OpportunityScoringAgent
from app.core.database import session_scope
from app.core.logging import get_logger
from app.models.admin import AIUsage, CostTracking
from app.models.agent import AIMemory
from app.models.campaign import ResearchJob
from app.models.company import Company
from app.models.enums import JobStatus
from app.services.research import run_research_job
from app.workers.celery_app import celery_app  # noqa: F401  (ensures the app is configured)

logger = get_logger(__name__)


@shared_task(name="research.run_job", bind=True, max_retries=1)
def run_research_job_task(self, job_id: str, max_companies: int | None = None) -> dict:
    """Run one research job. The orchestrator owns all progress reporting."""
    logger.info("worker_job_started", job_id=job_id, task_id=self.request.id)
    with session_scope() as db:
        job = db.get(ResearchJob, uuid.UUID(job_id))
        if job is not None:
            job.celery_task_id = self.request.id
    return run_research_job(job_id, max_companies=max_companies)


@shared_task(name="research.rescore_company")
def rescore_company_task(company_id: str, offered_services: list[str] | None = None) -> dict:
    """Recompute a single company's score, e.g. after admin weights change."""
    with session_scope() as db:
        company = db.get(Company, uuid.UUID(company_id))
        if company is None:
            return {"ok": False, "error": "company_not_found"}
        ctx = AgentContext(
            db=db, organization_id=company.organization_id, company_id=company.id
        )
        result = asyncio.run(
            OpportunityScoringAgent().execute(
                ctx,
                {
                    "company_id": company_id,
                    "offered_services": offered_services or [],
                    "opportunities": (company.research.opportunities if company.research else []),
                },
            )
        )
        return {"ok": result.ok, "total": result.data.get("total")}


@shared_task(name="maintenance.rollup_costs")
def rollup_costs_task() -> dict:
    """Aggregate yesterday's token spend into the daily cost table."""
    day = (datetime.now(UTC) - timedelta(days=1)).date()
    start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    end = start + timedelta(days=1)
    rolled = 0

    with session_scope() as db:
        rows = db.execute(
            select(AIUsage.organization_id, func.sum(AIUsage.cost_usd))
            .where(AIUsage.created_at >= start, AIUsage.created_at < end)
            .group_by(AIUsage.organization_id)
        ).all()
        for organization_id, cost in rows:
            prospects = db.execute(
                select(func.count(Company.id)).where(
                    Company.organization_id == organization_id,
                    Company.created_at >= start,
                    Company.created_at < end,
                    Company.is_rejected.is_(False),
                )
            ).scalar_one()
            existing = db.execute(
                select(CostTracking).where(
                    CostTracking.organization_id == organization_id, CostTracking.day == day
                )
            ).scalar_one_or_none()
            record = existing or CostTracking(organization_id=organization_id, day=day)
            record.llm_cost_usd = float(cost or 0.0)
            record.total_cost_usd = float(cost or 0.0) + record.connector_cost_usd
            record.prospects_produced = prospects
            record.cost_per_prospect_usd = (
                round(record.total_cost_usd / prospects, 6) if prospects else 0.0
            )
            if existing is None:
                db.add(record)
            rolled += 1
    return {"ok": True, "organizations": rolled, "day": str(day)}


@shared_task(name="maintenance.expire_memory")
def expire_memory_task() -> dict:
    now = datetime.now(UTC)
    with session_scope() as db:
        stale = (
            db.execute(select(AIMemory).where(AIMemory.expires_at.isnot(None), AIMemory.expires_at < now))
            .scalars()
            .all()
        )
        for row in stale:
            db.delete(row)
    return {"ok": True, "expired": len(stale)}


@shared_task(name="maintenance.reap_stuck_jobs")
def reap_stuck_jobs_task(stale_minutes: int = 90) -> dict:
    """Fail jobs whose worker died so the UI never shows a job running forever."""
    cutoff = datetime.now(UTC) - timedelta(minutes=stale_minutes)
    reaped = 0
    with session_scope() as db:
        jobs = (
            db.execute(
                select(ResearchJob).where(
                    ResearchJob.status == JobStatus.RUNNING, ResearchJob.updated_at < cutoff
                )
            )
            .scalars()
            .all()
        )
        for job in jobs:
            job.status = JobStatus.FAILED
            job.error = f"No progress for {stale_minutes} minutes; the worker was lost."
            job.finished_at = datetime.now(UTC)
            reaped += 1
    return {"ok": True, "reaped": reaped}
