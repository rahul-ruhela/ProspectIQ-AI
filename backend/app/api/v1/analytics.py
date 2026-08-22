"""Dashboard metrics and analytics aggregations."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession, OrgId
from app.models.admin import AIUsage
from app.models.agent import Agent, AgentTask
from app.models.campaign import ResearchJob
from app.models.company import Company, PipelineEntry, Technology
from app.models.enums import PIPELINE_ORDER, AgentStatus, JobStatus, PipelineStage
from app.schemas.crm import AnalyticsOverview, DashboardMetrics, TimeseriesPoint

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/dashboard", response_model=DashboardMetrics)
def dashboard(db: DbSession, organization_id: OrgId, _: CurrentUser) -> DashboardMetrics:
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    def company_count(*conditions) -> int:
        return db.execute(
            select(func.count(Company.id)).where(
                Company.organization_id == organization_id, *conditions
            )
        ).scalar_one()

    def stage_count(*stages: PipelineStage) -> int:
        return db.execute(
            select(func.count(PipelineEntry.id)).where(
                PipelineEntry.organization_id == organization_id,
                PipelineEntry.stage.in_(stages),
            )
        ).scalar_one()

    avg_score = db.execute(
        select(func.avg(Company.opportunity_score)).where(
            Company.organization_id == organization_id,
            Company.opportunity_score.isnot(None),
            Company.is_rejected.is_(False),
        )
    ).scalar_one()

    spend = db.execute(
        select(func.sum(AIUsage.cost_usd)).where(
            AIUsage.organization_id == organization_id, AIUsage.created_at >= month_ago
        )
    ).scalar_one() or 0.0

    qualified = company_count(Company.is_rejected.is_(False), Company.opportunity_score >= 60)
    follow_ups = db.execute(
        select(func.count(PipelineEntry.id)).where(
            PipelineEntry.organization_id == organization_id,
            PipelineEntry.next_follow_up_at.isnot(None),
            PipelineEntry.next_follow_up_at <= now + timedelta(days=7),
        )
    ).scalar_one()

    return DashboardMetrics(
        companies_total=company_count(),
        companies_new_7d=company_count(Company.created_at >= week_ago),
        qualified_total=qualified,
        ready_to_contact=stage_count(PipelineStage.READY_CONTACT, PipelineStage.QUALIFIED),
        contacted_total=stage_count(
            PipelineStage.CONTACTED, PipelineStage.REPLY_RECEIVED, PipelineStage.MEETING
        ),
        customers_total=stage_count(PipelineStage.CUSTOMER),
        avg_opportunity_score=round(float(avg_score or 0.0), 1),
        active_jobs=db.execute(
            select(func.count(ResearchJob.id)).where(
                ResearchJob.organization_id == organization_id,
                ResearchJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        ).scalar_one(),
        agents_running=db.execute(
            select(func.count(Agent.id)).where(Agent.status == AgentStatus.RUNNING)
        ).scalar_one(),
        spend_30d_usd=round(float(spend), 4),
        cost_per_prospect_usd=round(float(spend) / qualified, 4) if qualified else 0.0,
        follow_ups_due=follow_ups,
    )


@router.get("/overview", response_model=AnalyticsOverview)
def overview(
    db: DbSession, organization_id: OrgId, _: CurrentUser, days: int = Query(30, ge=7, le=365)
) -> AnalyticsOverview:
    since = datetime.now(UTC) - timedelta(days=days)

    discovery = db.execute(
        select(func.date(Company.created_at), func.count(Company.id))
        .where(Company.organization_id == organization_id, Company.created_at >= since)
        .group_by(func.date(Company.created_at))
        .order_by(func.date(Company.created_at))
    ).all()

    distribution = dict(
        db.execute(
            select(Company.opportunity_category, func.count(Company.id))
            .where(
                Company.organization_id == organization_id,
                Company.opportunity_category.isnot(None),
                Company.is_rejected.is_(False),
            )
            .group_by(Company.opportunity_category)
        ).all()
    )

    industries = db.execute(
        select(
            Company.industry_slug,
            func.count(Company.id),
            func.avg(Company.opportunity_score),
        )
        .where(Company.organization_id == organization_id, Company.industry_slug.isnot(None))
        .group_by(Company.industry_slug)
        .order_by(func.count(Company.id).desc())
        .limit(10)
    ).all()

    countries = db.execute(
        select(Company.country_code, func.count(Company.id), func.avg(Company.opportunity_score))
        .where(Company.organization_id == organization_id, Company.country_code.isnot(None))
        .group_by(Company.country_code)
        .order_by(func.count(Company.id).desc())
        .limit(12)
    ).all()

    technologies = db.execute(
        select(Technology.name, func.count(Technology.id))
        .join(Company, Company.id == Technology.company_id)
        .where(Company.organization_id == organization_id)
        .group_by(Technology.name)
        .order_by(func.count(Technology.id).desc())
        .limit(12)
    ).all()

    stage_counts = dict(
        db.execute(
            select(PipelineEntry.stage, func.count(PipelineEntry.id))
            .where(PipelineEntry.organization_id == organization_id)
            .group_by(PipelineEntry.stage)
        ).all()
    )

    costs = db.execute(
        select(func.date(AIUsage.created_at), func.sum(AIUsage.cost_usd))
        .where(AIUsage.organization_id == organization_id, AIUsage.created_at >= since)
        .group_by(func.date(AIUsage.created_at))
        .order_by(func.date(AIUsage.created_at))
    ).all()

    agent_rows = db.execute(
        select(
            AgentTask.agent_key,
            func.count(AgentTask.id),
            func.avg(AgentTask.confidence),
        )
        .where(AgentTask.organization_id == organization_id)
        .group_by(AgentTask.agent_key)
        .order_by(func.count(AgentTask.id).desc())
    ).all()

    return AnalyticsOverview(
        discovery_trend=[TimeseriesPoint(date=str(d), value=float(c)) for d, c in discovery],
        score_distribution={str(k): int(v) for k, v in distribution.items()},
        top_industries=[
            {"industry": slug, "companies": int(count), "avg_score": round(float(avg or 0), 1)}
            for slug, count, avg in industries
        ],
        top_countries=[
            {"country": code, "companies": int(count), "avg_score": round(float(avg or 0), 1)}
            for code, count, avg in countries
        ],
        top_technologies=[{"technology": name, "companies": int(count)} for name, count in technologies],
        pipeline_funnel=[
            {"stage": str(stage), "count": int(stage_counts.get(stage, 0))} for stage in PIPELINE_ORDER
        ],
        cost_trend=[TimeseriesPoint(date=str(d), value=round(float(c or 0), 4)) for d, c in costs],
        agent_performance=[
            {
                "agent": key,
                "tasks": int(count),
                "avg_confidence": round(float(confidence or 0), 3),
            }
            for key, count, confidence in agent_rows
        ],
    )
