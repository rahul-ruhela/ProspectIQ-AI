"""Company and prospect endpoints, including report approval and CSV export."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DbSession, OrgId, RequireResearcher, RequireSales, audit
from app.models.company import AIResearch, Company, Contact, PipelineEntry
from app.models.enums import PipelineStage, ScoreCategory
from app.schemas.common import Message, Page
from app.schemas.company import (
    AIResearchOut,
    ApproveReportRequest,
    CompanyDetail,
    CompanyListItem,
)

router = APIRouter(prefix="/companies", tags=["Companies"])

SORTABLE = {
    "opportunity_score": Company.opportunity_score,
    "lead_quality_score": Company.lead_quality_score,
    "name": Company.name,
    "created_at": Company.created_at,
    "last_researched_at": Company.last_researched_at,
    "data_completeness": Company.data_completeness,
}


def _detail_query():
    return select(Company).options(
        selectinload(Company.sources),
        selectinload(Company.technologies),
        selectinload(Company.contacts).selectinload(Contact.email_verification),
        selectinload(Company.contacts).selectinload(Contact.phone_verification),
        selectinload(Company.decision_makers),
        selectinload(Company.signals),
        selectinload(Company.score),
        selectinload(Company.research).selectinload(AIResearch.findings),
        selectinload(Company.website_record),
    )


@router.get("", response_model=Page[CompanyListItem])
def list_companies(
    db: DbSession,
    organization_id: OrgId,
    _: CurrentUser,
    q: str | None = None,
    campaign_id: uuid.UUID | None = None,
    country_code: str | None = None,
    industry_slug: str | None = None,
    category: ScoreCategory | None = None,
    min_score: float | None = Query(None, ge=0, le=100),
    max_score: float | None = Query(None, ge=0, le=100),
    has_contact: bool | None = None,
    include_rejected: bool = False,
    sort_by: str = "opportunity_score",
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> Page[CompanyListItem]:
    stmt = select(Company).where(Company.organization_id == organization_id)
    if not include_rejected:
        stmt = stmt.where(Company.is_rejected.is_(False))
    if q:
        needle = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Company.name).like(needle),
                func.lower(Company.domain).like(needle),
                func.lower(Company.description).like(needle),
            )
        )
    if campaign_id:
        stmt = stmt.where(Company.campaign_id == campaign_id)
    if country_code:
        stmt = stmt.where(Company.country_code == country_code.upper())
    if industry_slug:
        stmt = stmt.where(Company.industry_slug == industry_slug)
    if category:
        stmt = stmt.where(Company.opportunity_category == category)
    if min_score is not None:
        stmt = stmt.where(Company.opportunity_score >= min_score)
    if max_score is not None:
        stmt = stmt.where(Company.opportunity_score <= max_score)
    if has_contact is not None:
        exists = select(Contact.id).where(Contact.company_id == Company.id).exists()
        stmt = stmt.where(exists if has_contact else ~exists)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    column = SORTABLE.get(sort_by, Company.opportunity_score)
    order = column.desc().nullslast() if sort_dir == "desc" else column.asc().nullsfirst()
    rows = (
        db.execute(stmt.order_by(order).offset((page - 1) * page_size).limit(page_size))
        .scalars()
        .all()
    )
    return Page[CompanyListItem](
        items=[CompanyListItem.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


def _get_company(db: DbSession, company_id: uuid.UUID, organization_id: uuid.UUID) -> Company:
    company = db.execute(
        _detail_query().where(Company.id == company_id, Company.organization_id == organization_id)
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


@router.get("/export", response_class=Response)
def export_companies(
    db: DbSession,
    organization_id: OrgId,
    user: CurrentUser,
    campaign_id: uuid.UUID | None = None,
    min_score: float = Query(0, ge=0, le=100),
    include_rejected: bool = False,
) -> Response:
    """CSV of prospects with their provenance columns intact."""
    stmt = select(Company).where(
        Company.organization_id == organization_id,
        or_(Company.opportunity_score >= min_score, Company.opportunity_score.is_(None)),
    )
    if campaign_id:
        stmt = stmt.where(Company.campaign_id == campaign_id)
    if not include_rejected:
        stmt = stmt.where(Company.is_rejected.is_(False))
    rows = db.execute(stmt.order_by(Company.opportunity_score.desc().nullslast())).scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Company", "Domain", "Website", "Industry", "Country", "City", "Employees",
            "Opportunity Score", "Category", "Lead Quality", "Data Completeness",
            "Primary Email", "Phone", "Decision Maker", "Decision Maker Role",
            "Recommended Services", "Technologies", "Source", "Source URL",
            "Confidence", "Verification Status", "Last Verified", "Why Contact",
        ]
    )
    for company in rows:
        primary_dm = company.decision_makers[0] if company.decision_makers else None
        writer.writerow(
            [
                company.name,
                company.domain or "Unknown",
                company.website or "Unknown",
                company.industry_slug or "Unknown",
                company.country_code or "Unknown",
                company.city or "Unknown",
                company.employee_count if company.employee_count else "Unknown",
                company.opportunity_score if company.opportunity_score is not None else "",
                company.opportunity_category or "",
                company.lead_quality_score if company.lead_quality_score is not None else "",
                company.data_completeness,
                company.primary_email or "Unknown",
                company.phone or "Unknown",
                primary_dm.full_name if primary_dm else "Unknown",
                (primary_dm.role_title or "Unknown") if primary_dm else "Unknown",
                ", ".join(company.score.recommended_services) if company.score else "",
                ", ".join(t.name for t in company.technologies),
                company.source or "Unknown",
                company.source_url or "",
                company.confidence,
                company.verification_status,
                company.last_verified_at.isoformat() if company.last_verified_at else "",
                (company.research.why_contact_them if company.research else "") or "",
            ]
        )

    audit(db, user=user, action="company.export", entity_type="company", detail=f"{len(rows)} rows")
    db.commit()
    filename = f"prospectiq-export-{datetime.now(UTC):%Y%m%d-%H%M}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{company_id}", response_model=CompanyDetail)
def get_company(
    company_id: uuid.UUID, db: DbSession, organization_id: OrgId, _: CurrentUser
) -> CompanyDetail:
    return CompanyDetail.model_validate(_get_company(db, company_id, organization_id))


@router.get("/{company_id}/report", response_model=AIResearchOut)
def get_report(
    company_id: uuid.UUID, db: DbSession, organization_id: OrgId, _: CurrentUser
) -> AIResearchOut:
    company = _get_company(db, company_id, organization_id)
    if company.research is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No report has been generated for this company yet.",
        )
    return AIResearchOut.model_validate(company.research)


@router.post("/{company_id}/report/approve", response_model=AIResearchOut)
def approve_report(
    company_id: uuid.UUID,
    payload: ApproveReportRequest,
    user: RequireSales,
    db: DbSession,
    organization_id: OrgId,
) -> AIResearchOut:
    """Human approval gate. Nothing is sent by the platform; this records sign-off."""
    company = _get_company(db, company_id, organization_id)
    if company.research is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No report to approve")

    if payload.approved:
        company.research.approved_by_id = user.id
        company.research.approved_at = datetime.now(UTC)
        if company.pipeline is None:
            company.pipeline = PipelineEntry(
                organization_id=organization_id,
                company_id=company.id,
                stage=PipelineStage.READY_CONTACT,
            )
        elif company.pipeline.stage in (PipelineStage.DISCOVERED, PipelineStage.RESEARCHING, PipelineStage.QUALIFIED):
            company.pipeline.stage = PipelineStage.READY_CONTACT
    else:
        company.research.approved_by_id = None
        company.research.approved_at = None

    audit(
        db,
        user=user,
        action="report.approve" if payload.approved else "report.unapprove",
        entity_type="company",
        entity_id=str(company.id),
        detail=payload.note,
    )
    db.commit()
    db.refresh(company)
    return AIResearchOut.model_validate(company.research)


@router.post("/{company_id}/reject", response_model=Message)
def reject_company(
    company_id: uuid.UUID,
    user: RequireResearcher,
    db: DbSession,
    organization_id: OrgId,
    reason: str = Query(..., min_length=3, max_length=400),
) -> Message:
    company = _get_company(db, company_id, organization_id)
    company.is_rejected = True
    company.rejection_reason = reason
    audit(db, user=user, action="company.reject", entity_type="company", entity_id=str(company.id), detail=reason)
    db.commit()
    return Message(detail="Company rejected")


@router.post("/{company_id}/rescore", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
def rescore_company(
    company_id: uuid.UUID, user: RequireResearcher, db: DbSession, organization_id: OrgId
) -> Message:
    company = _get_company(db, company_id, organization_id)
    offered = (
        company.score.recommended_services if company.score else []
    )
    try:
        from app.workers.tasks import rescore_company_task

        rescore_company_task.delay(str(company.id), offered)
        return Message(detail="Re-scoring queued")
    except Exception:
        # Without a broker, do it synchronously rather than failing the request.
        import asyncio

        from app.agents.base import AgentContext
        from app.agents.quality import OpportunityScoringAgent

        ctx = AgentContext(db=db, organization_id=organization_id, company_id=company.id)
        asyncio.run(
            OpportunityScoringAgent().execute(
                ctx,
                {
                    "company_id": str(company.id),
                    "offered_services": offered,
                    "opportunities": company.research.opportunities if company.research else [],
                },
            )
        )
        db.commit()
        return Message(detail="Re-scored inline (no worker queue available)")
