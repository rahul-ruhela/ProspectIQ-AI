"""Campaign CRUD and the one-click START RESEARCH endpoint."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, OrgId, RequireResearcher, audit
from app.core.logging import get_logger
from app.models.campaign import Campaign, CampaignFilter, ResearchJob
from app.models.company import Company, PipelineEntry
from app.models.enums import CampaignStatus, JobStatus, PipelineStage
from app.schemas.campaign import (
    CampaignCreate,
    CampaignOut,
    CampaignStats,
    CampaignUpdate,
    ResearchJobOut,
    StartResearchRequest,
)
from app.schemas.common import Message, Page

logger = get_logger(__name__)
router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


def _get_campaign(db: DbSession, campaign_id: uuid.UUID, organization_id: uuid.UUID) -> Campaign:
    campaign = db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


@router.get("", response_model=Page[CampaignOut])
def list_campaigns(
    db: DbSession,
    organization_id: OrgId,
    _: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    campaign_status: CampaignStatus | None = None,
) -> Page[CampaignOut]:
    stmt = select(Campaign).where(Campaign.organization_id == organization_id)
    if campaign_status:
        stmt = stmt.where(Campaign.status == campaign_status)
    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()
    rows = (
        db.execute(stmt.order_by(Campaign.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
    return Page[CampaignOut](
        items=[CampaignOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate, user: RequireResearcher, db: DbSession, organization_id: OrgId
) -> CampaignOut:
    campaign = Campaign(
        organization_id=organization_id,
        created_by_id=user.id,
        name=payload.name,
        objective=payload.objective,
        target_prospect_count=payload.target_prospect_count,
        budget_usd=payload.budget_usd or settings.DEFAULT_CAMPAIGN_BUDGET_USD,
        offered_services=[str(s) for s in payload.offered_services],
        status=CampaignStatus.DRAFT,
    )
    campaign.filters = CampaignFilter(**payload.filters.model_dump())
    db.add(campaign)
    audit(db, user=user, action="campaign.create", entity_type="campaign", detail=payload.name)
    db.commit()
    db.refresh(campaign)
    return CampaignOut.model_validate(campaign)


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: uuid.UUID, db: DbSession, organization_id: OrgId, _: CurrentUser) -> CampaignOut:
    return CampaignOut.model_validate(_get_campaign(db, campaign_id, organization_id))


@router.patch("/{campaign_id}", response_model=CampaignOut)
def update_campaign(
    campaign_id: uuid.UUID,
    payload: CampaignUpdate,
    user: RequireResearcher,
    db: DbSession,
    organization_id: OrgId,
) -> CampaignOut:
    campaign = _get_campaign(db, campaign_id, organization_id)
    data = payload.model_dump(exclude_unset=True)
    filters = data.pop("filters", None)
    services = data.pop("offered_services", None)
    for field, value in data.items():
        setattr(campaign, field, value)
    if services is not None:
        campaign.offered_services = [str(s) for s in services]
    if filters is not None:
        if campaign.filters is None:
            campaign.filters = CampaignFilter(**filters)
        else:
            for field, value in filters.items():
                setattr(campaign.filters, field, value)
    audit(db, user=user, action="campaign.update", entity_type="campaign", entity_id=str(campaign.id))
    db.commit()
    db.refresh(campaign)
    return CampaignOut.model_validate(campaign)


@router.delete("/{campaign_id}", response_model=Message)
def delete_campaign(
    campaign_id: uuid.UUID, user: RequireResearcher, db: DbSession, organization_id: OrgId
) -> Message:
    campaign = _get_campaign(db, campaign_id, organization_id)
    campaign.status = CampaignStatus.ARCHIVED
    audit(db, user=user, action="campaign.archive", entity_type="campaign", entity_id=str(campaign.id))
    db.commit()
    return Message(detail="Campaign archived")


@router.get("/{campaign_id}/stats", response_model=CampaignStats)
def campaign_stats(
    campaign_id: uuid.UUID, db: DbSession, organization_id: OrgId, _: CurrentUser
) -> CampaignStats:
    campaign = _get_campaign(db, campaign_id, organization_id)
    companies = db.execute(
        select(func.count(Company.id)).where(Company.campaign_id == campaign.id)
    ).scalar_one()
    qualified = db.execute(
        select(func.count(Company.id)).where(
            Company.campaign_id == campaign.id, Company.is_rejected.is_(False)
        )
    ).scalar_one()
    ready = db.execute(
        select(func.count(PipelineEntry.id))
        .join(Company, Company.id == PipelineEntry.company_id)
        .where(
            Company.campaign_id == campaign.id,
            PipelineEntry.stage.in_([PipelineStage.QUALIFIED, PipelineStage.READY_CONTACT]),
        )
    ).scalar_one()
    avg_score = db.execute(
        select(func.avg(Company.opportunity_score)).where(
            Company.campaign_id == campaign.id, Company.opportunity_score.isnot(None)
        )
    ).scalar_one() or 0.0
    return CampaignStats(
        campaign_id=campaign.id,
        companies=companies,
        qualified=qualified,
        ready_to_contact=ready,
        avg_opportunity_score=round(float(avg_score), 1),
        total_cost_usd=round(campaign.spent_usd, 4),
        cost_per_prospect_usd=round(campaign.spent_usd / qualified, 4) if qualified else 0.0,
    )


@router.post(
    "/{campaign_id}/start", response_model=ResearchJobOut, status_code=status.HTTP_202_ACCEPTED
)
def start_research(
    campaign_id: uuid.UUID,
    payload: StartResearchRequest,
    user: RequireResearcher,
    db: DbSession,
    organization_id: OrgId,
) -> ResearchJobOut:
    """One click: create the job and hand it to the CEO orchestrator."""
    campaign = _get_campaign(db, campaign_id, organization_id)
    if campaign.filters is None or not campaign.filters.countries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one country before starting research.",
        )

    running = db.execute(
        select(ResearchJob).where(
            ResearchJob.campaign_id == campaign.id,
            ResearchJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    ).scalar_one_or_none()
    if running is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A research job is already running for this campaign.",
        )

    job = ResearchJob(
        organization_id=organization_id,
        campaign_id=campaign.id,
        triggered_by_id=user.id,
        status=JobStatus.QUEUED,
        current_stage="Queued",
    )
    campaign.status = CampaignStatus.ACTIVE
    db.add(job)
    audit(db, user=user, action="research.start", entity_type="campaign", entity_id=str(campaign.id))
    db.commit()
    db.refresh(job)

    from app.services.research import dispatch_job

    dispatch_job(db, job, max_companies=payload.max_companies, run_inline=payload.run_inline)
    db.refresh(job)
    return ResearchJobOut.model_validate(job)


# --- research jobs -------------------------------------------------------------

jobs_router = APIRouter(prefix="/jobs", tags=["Research Jobs"])


@jobs_router.get("", response_model=Page[ResearchJobOut])
def list_jobs(
    db: DbSession,
    organization_id: OrgId,
    _: CurrentUser,
    campaign_id: uuid.UUID | None = None,
    job_status: JobStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> Page[ResearchJobOut]:
    stmt = select(ResearchJob).where(ResearchJob.organization_id == organization_id)
    if campaign_id:
        stmt = stmt.where(ResearchJob.campaign_id == campaign_id)
    if job_status:
        stmt = stmt.where(ResearchJob.status == job_status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(ResearchJob.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return Page[ResearchJobOut](
        items=[ResearchJobOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


def _get_job(db: DbSession, job_id: uuid.UUID, organization_id: uuid.UUID) -> ResearchJob:
    job = db.execute(
        select(ResearchJob).where(
            ResearchJob.id == job_id, ResearchJob.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research job not found")
    return job


@jobs_router.get("/{job_id}", response_model=ResearchJobOut)
def get_job(job_id: uuid.UUID, db: DbSession, organization_id: OrgId, _: CurrentUser) -> ResearchJobOut:
    return ResearchJobOut.model_validate(_get_job(db, job_id, organization_id))


@jobs_router.post("/{job_id}/cancel", response_model=ResearchJobOut)
def cancel_job(
    job_id: uuid.UUID, user: RequireResearcher, db: DbSession, organization_id: OrgId
) -> ResearchJobOut:
    job = _get_job(db, job_id, organization_id)
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job already finished")
    # The orchestrator checks this flag between companies so work stops cleanly.
    job.cancel_requested = True
    if job.status == JobStatus.QUEUED:
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now(UTC)
    audit(db, user=user, action="research.cancel", entity_type="research_job", entity_id=str(job.id))
    db.commit()
    db.refresh(job)
    return ResearchJobOut.model_validate(job)


@jobs_router.post("/{job_id}/pause", response_model=ResearchJobOut)
def pause_job(
    job_id: uuid.UUID, user: RequireResearcher, db: DbSession, organization_id: OrgId
) -> ResearchJobOut:
    job = _get_job(db, job_id, organization_id)
    if job.status != JobStatus.RUNNING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job is not running")
    job.cancel_requested = True
    job.status = JobStatus.PAUSED
    audit(db, user=user, action="research.pause", entity_type="research_job", entity_id=str(job.id))
    db.commit()
    db.refresh(job)
    return ResearchJobOut.model_validate(job)


@jobs_router.post("/{job_id}/resume", response_model=ResearchJobOut)
def resume_job(
    job_id: uuid.UUID, user: RequireResearcher, db: DbSession, organization_id: OrgId
) -> ResearchJobOut:
    job = _get_job(db, job_id, organization_id)
    if job.status not in (JobStatus.PAUSED, JobStatus.FAILED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Only paused or failed jobs can resume"
        )
    job.cancel_requested = False
    job.status = JobStatus.QUEUED
    job.error = None
    db.commit()

    from app.services.research import dispatch_job

    dispatch_job(db, job)
    db.refresh(job)
    return ResearchJobOut.model_validate(job)
