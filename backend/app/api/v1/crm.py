"""CRM pipeline, contact tracking, activities and human feedback."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DbSession, OrgId, RequireSales, audit
from app.models.company import Activity, Company, HumanFeedback, PipelineEntry
from app.models.enums import PIPELINE_ORDER, ActivityType, ContactStatus, PipelineStage
from app.models.org import User
from app.schemas.common import Message
from app.schemas.crm import (
    ActivityCreate,
    ActivityOut,
    AssignRequest,
    ContactStatusRequest,
    FeedbackCreate,
    PipelineBoard,
    PipelineCard,
    StageChangeRequest,
)

router = APIRouter(prefix="/crm", tags=["CRM"])


def _card(entry: PipelineEntry, company: Company, user_name: str | None) -> PipelineCard:
    return PipelineCard(
        id=entry.id,
        company_id=entry.company_id,
        stage=entry.stage,
        contact_status=entry.contact_status,
        assigned_user_id=entry.assigned_user_id,
        last_contact_at=entry.last_contact_at,
        last_action=entry.last_action,
        next_follow_up_at=entry.next_follow_up_at,
        contact_attempts=entry.contact_attempts,
        deal_value_usd=entry.deal_value_usd,
        lost_reason=entry.lost_reason,
        notes=entry.notes,
        updated_at=entry.updated_at,
        company_name=company.name,
        company_domain=company.domain,
        country_code=company.country_code,
        opportunity_score=company.opportunity_score,
        assigned_user_name=user_name,
    )


@router.get("/pipeline", response_model=PipelineBoard)
def get_pipeline(
    db: DbSession,
    organization_id: OrgId,
    _: CurrentUser,
    assigned_user_id: uuid.UUID | None = None,
    min_score: float | None = Query(None, ge=0, le=100),
    limit_per_stage: int = Query(50, ge=1, le=200),
) -> PipelineBoard:
    stmt = (
        select(PipelineEntry, Company)
        .join(Company, Company.id == PipelineEntry.company_id)
        .where(PipelineEntry.organization_id == organization_id)
    )
    if assigned_user_id:
        stmt = stmt.where(PipelineEntry.assigned_user_id == assigned_user_id)
    if min_score is not None:
        stmt = stmt.where(Company.opportunity_score >= min_score)

    rows = db.execute(stmt.order_by(Company.opportunity_score.desc().nullslast())).all()
    names = {
        u.id: u.full_name
        for u in db.execute(select(User).where(User.organization_id == organization_id)).scalars()
    }

    stages: dict[str, list[PipelineCard]] = {str(s): [] for s in PIPELINE_ORDER}
    counts: dict[str, int] = {str(s): 0 for s in PIPELINE_ORDER}
    total_value = 0.0
    for entry, company in rows:
        key = str(entry.stage)
        counts[key] = counts.get(key, 0) + 1
        if len(stages.setdefault(key, [])) < limit_per_stage:
            stages[key].append(_card(entry, company, names.get(entry.assigned_user_id)))
        if entry.deal_value_usd and entry.stage not in (PipelineStage.LOST,):
            total_value += entry.deal_value_usd

    return PipelineBoard(stages=stages, counts=counts, total_value_usd=round(total_value, 2))


def _get_entry(db: DbSession, company_id: uuid.UUID, organization_id: uuid.UUID) -> PipelineEntry:
    entry = db.execute(
        select(PipelineEntry)
        .options(selectinload(PipelineEntry.company))
        .where(
            PipelineEntry.company_id == company_id,
            PipelineEntry.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if entry is None:
        company = db.execute(
            select(Company).where(
                Company.id == company_id, Company.organization_id == organization_id
            )
        ).scalar_one_or_none()
        if company is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        entry = PipelineEntry(organization_id=organization_id, company_id=company.id)
        db.add(entry)
        db.flush()
    return entry


@router.post("/{company_id}/stage", response_model=PipelineCard)
def change_stage(
    company_id: uuid.UUID,
    payload: StageChangeRequest,
    user: RequireSales,
    db: DbSession,
    organization_id: OrgId,
) -> PipelineCard:
    entry = _get_entry(db, company_id, organization_id)
    previous = entry.stage
    entry.stage = payload.stage
    if payload.deal_value_usd is not None:
        entry.deal_value_usd = payload.deal_value_usd
    if payload.stage == PipelineStage.LOST:
        entry.lost_reason = payload.lost_reason

    db.add(
        Activity(
            organization_id=organization_id,
            pipeline_entry_id=entry.id,
            company_id=company_id,
            user_id=user.id,
            activity_type=ActivityType.STAGE_CHANGE,
            title=f"Stage changed from {previous} to {payload.stage}",
            body=payload.note,
            occurred_at=datetime.now(UTC),
        )
    )
    audit(db, user=user, action="crm.stage_change", entity_type="company", entity_id=str(company_id),
          detail=f"{previous} -> {payload.stage}")
    db.commit()
    db.refresh(entry)
    company = db.get(Company, company_id)
    return _card(entry, company, user.full_name if entry.assigned_user_id == user.id else None)


@router.post("/{company_id}/contact-status", response_model=PipelineCard)
def set_contact_status(
    company_id: uuid.UUID,
    payload: ContactStatusRequest,
    user: RequireSales,
    db: DbSession,
    organization_id: OrgId,
) -> PipelineCard:
    """Records an outreach attempt so the same prospect is never called twice blindly."""
    entry = _get_entry(db, company_id, organization_id)
    entry.contact_status = payload.contact_status
    entry.last_action = payload.last_action or str(payload.contact_status)
    entry.next_follow_up_at = payload.next_follow_up_at

    if payload.contact_status in (
        ContactStatus.CALLED,
        ContactStatus.CONTACTED,
        ContactStatus.FOLLOW_UP_REQUIRED,
    ):
        entry.last_contact_at = datetime.now(UTC)
        entry.contact_attempts += 1
        if entry.stage in (
            PipelineStage.DISCOVERED,
            PipelineStage.RESEARCHING,
            PipelineStage.QUALIFIED,
            PipelineStage.READY_CONTACT,
        ):
            entry.stage = PipelineStage.CONTACTED
    if payload.contact_status == ContactStatus.MEETING_SCHEDULED:
        entry.stage = PipelineStage.MEETING
    if payload.contact_status == ContactStatus.NOT_INTERESTED:
        entry.stage = PipelineStage.LOST
        entry.lost_reason = entry.lost_reason or "Prospect not interested"
    if payload.contact_status == ContactStatus.CONVERTED:
        entry.stage = PipelineStage.CUSTOMER

    db.add(
        Activity(
            organization_id=organization_id,
            pipeline_entry_id=entry.id,
            company_id=company_id,
            user_id=user.id,
            activity_type=ActivityType.CALL
            if payload.contact_status == ContactStatus.CALLED
            else ActivityType.NOTE,
            title=f"Contact status set to {payload.contact_status}",
            body=payload.note,
            occurred_at=datetime.now(UTC),
        )
    )
    audit(db, user=user, action="crm.contact_status", entity_type="company", entity_id=str(company_id))
    db.commit()
    db.refresh(entry)
    company = db.get(Company, company_id)
    return _card(entry, company, user.full_name)


@router.post("/{company_id}/assign", response_model=PipelineCard)
def assign(
    company_id: uuid.UUID,
    payload: AssignRequest,
    user: RequireSales,
    db: DbSession,
    organization_id: OrgId,
) -> PipelineCard:
    entry = _get_entry(db, company_id, organization_id)
    assignee_name: str | None = None
    if payload.assigned_user_id is not None:
        assignee = db.execute(
            select(User).where(
                User.id == payload.assigned_user_id, User.organization_id == organization_id
            )
        ).scalar_one_or_none()
        if assignee is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")
        assignee_name = assignee.full_name
    entry.assigned_user_id = payload.assigned_user_id

    db.add(
        Activity(
            organization_id=organization_id,
            pipeline_entry_id=entry.id,
            company_id=company_id,
            user_id=user.id,
            activity_type=ActivityType.ASSIGNMENT,
            title=f"Assigned to {assignee_name or 'nobody'}",
            occurred_at=datetime.now(UTC),
        )
    )
    db.commit()
    db.refresh(entry)
    company = db.get(Company, company_id)
    return _card(entry, company, assignee_name)


@router.get("/{company_id}/activities", response_model=list[ActivityOut])
def list_activities(
    company_id: uuid.UUID, db: DbSession, organization_id: OrgId, _: CurrentUser
) -> list[ActivityOut]:
    rows = (
        db.execute(
            select(Activity)
            .where(Activity.company_id == company_id, Activity.organization_id == organization_id)
            .order_by(Activity.created_at.desc())
            .limit(200)
        )
        .scalars()
        .all()
    )
    return [ActivityOut.model_validate(r) for r in rows]


@router.post("/{company_id}/activities", response_model=ActivityOut, status_code=status.HTTP_201_CREATED)
def create_activity(
    company_id: uuid.UUID,
    payload: ActivityCreate,
    user: RequireSales,
    db: DbSession,
    organization_id: OrgId,
) -> ActivityOut:
    entry = _get_entry(db, company_id, organization_id)
    activity = Activity(
        organization_id=organization_id,
        pipeline_entry_id=entry.id,
        company_id=company_id,
        user_id=user.id,
        activity_type=payload.activity_type,
        title=payload.title,
        body=payload.body,
        occurred_at=payload.occurred_at or datetime.now(UTC),
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return ActivityOut.model_validate(activity)


@router.get("/follow-ups", response_model=list[PipelineCard])
def follow_ups(
    db: DbSession,
    organization_id: OrgId,
    user: CurrentUser,
    mine_only: bool = False,
    days_ahead: int = Query(7, ge=0, le=90),
) -> list[PipelineCard]:
    horizon = datetime.now(UTC).timestamp() + days_ahead * 86400
    stmt = (
        select(PipelineEntry, Company)
        .join(Company, Company.id == PipelineEntry.company_id)
        .where(
            PipelineEntry.organization_id == organization_id,
            PipelineEntry.next_follow_up_at.isnot(None),
        )
    )
    if mine_only:
        stmt = stmt.where(PipelineEntry.assigned_user_id == user.id)
    rows = db.execute(stmt.order_by(PipelineEntry.next_follow_up_at)).all()
    return [
        _card(entry, company, None)
        for entry, company in rows
        if entry.next_follow_up_at and entry.next_follow_up_at.timestamp() <= horizon
    ]


@router.post("/feedback", response_model=Message, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    payload: FeedbackCreate, user: RequireSales, db: DbSession, organization_id: OrgId
) -> Message:
    """Sales corrections that feed the scoring and prompt improvements."""
    db.add(
        HumanFeedback(
            organization_id=organization_id,
            company_id=payload.company_id,
            user_id=user.id,
            target=payload.target,
            verdict=payload.verdict,
            corrected_value=payload.corrected_value,
            comment=payload.comment,
        )
    )
    db.commit()
    return Message(detail="Feedback recorded")


@router.get("/stats", response_model=dict)
def crm_stats(db: DbSession, organization_id: OrgId, _: CurrentUser) -> dict:
    counts = dict(
        db.execute(
            select(PipelineEntry.stage, func.count(PipelineEntry.id))
            .where(PipelineEntry.organization_id == organization_id)
            .group_by(PipelineEntry.stage)
        ).all()
    )
    contact_counts = dict(
        db.execute(
            select(PipelineEntry.contact_status, func.count(PipelineEntry.id))
            .where(PipelineEntry.organization_id == organization_id)
            .group_by(PipelineEntry.contact_status)
        ).all()
    )
    return {
        "by_stage": {str(k): int(v) for k, v in counts.items()},
        "by_contact_status": {str(k): int(v) for k, v in contact_counts.items()},
    }
