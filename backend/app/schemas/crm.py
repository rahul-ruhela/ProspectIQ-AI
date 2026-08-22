"""CRM pipeline, activity and analytics schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ActivityType, ContactStatus, PipelineStage
from app.schemas.common import ORMModel


class PipelineEntryOut(ORMModel):
    id: uuid.UUID
    company_id: uuid.UUID
    stage: PipelineStage
    contact_status: ContactStatus
    assigned_user_id: uuid.UUID | None
    last_contact_at: datetime | None
    last_action: str | None
    next_follow_up_at: datetime | None
    contact_attempts: int
    deal_value_usd: float | None
    lost_reason: str | None
    notes: str | None
    updated_at: datetime


class PipelineCard(PipelineEntryOut):
    """Pipeline entry denormalised with the company fields the board needs."""

    company_name: str
    company_domain: str | None
    country_code: str | None
    opportunity_score: float | None
    assigned_user_name: str | None = None


class PipelineBoard(BaseModel):
    stages: dict[str, list[PipelineCard]]
    counts: dict[str, int]
    total_value_usd: float


class StageChangeRequest(BaseModel):
    stage: PipelineStage
    note: str | None = None
    lost_reason: str | None = None
    deal_value_usd: float | None = None


class ContactStatusRequest(BaseModel):
    contact_status: ContactStatus
    last_action: str | None = None
    next_follow_up_at: datetime | None = None
    note: str | None = None


class AssignRequest(BaseModel):
    assigned_user_id: uuid.UUID | None


class ActivityCreate(BaseModel):
    activity_type: ActivityType = ActivityType.NOTE
    title: str = Field(min_length=1, max_length=300)
    body: str | None = None
    occurred_at: datetime | None = None


class ActivityOut(ORMModel):
    id: uuid.UUID
    company_id: uuid.UUID | None
    user_id: uuid.UUID | None
    activity_type: str
    title: str
    body: str | None
    occurred_at: datetime | None
    created_at: datetime


class FeedbackCreate(BaseModel):
    company_id: uuid.UUID | None = None
    target: str = Field(default="score")
    verdict: str = Field(default="correct", pattern="^(correct|wrong|partial)$")
    corrected_value: str | None = None
    comment: str | None = None


class DashboardMetrics(BaseModel):
    companies_total: int
    companies_new_7d: int
    qualified_total: int
    ready_to_contact: int
    contacted_total: int
    customers_total: int
    avg_opportunity_score: float
    active_jobs: int
    agents_running: int
    spend_30d_usd: float
    cost_per_prospect_usd: float
    follow_ups_due: int


class TimeseriesPoint(BaseModel):
    date: str
    value: float


class AnalyticsOverview(BaseModel):
    discovery_trend: list[TimeseriesPoint]
    score_distribution: dict[str, int]
    top_industries: list[dict[str, float | str | int]]
    top_countries: list[dict[str, float | str | int]]
    top_technologies: list[dict[str, float | str | int]]
    pipeline_funnel: list[dict[str, int | str]]
    cost_trend: list[TimeseriesPoint]
    agent_performance: list[dict[str, float | str | int]]
