"""Campaign, filter and research-job schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import CampaignStatus, JobStatus, ServiceOffering
from app.schemas.common import ORMModel


class CampaignFilterIn(BaseModel):
    countries: list[str] = Field(default_factory=list, description="ISO-3166 alpha-2 codes")
    regions: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list, description="Industry slugs")
    business_types: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    employee_min: int | None = Field(default=None, ge=1)
    employee_max: int | None = Field(default=None, ge=1)
    min_opportunity_score: float = Field(default=40.0, ge=0, le=100)
    # A registered business without a website is the platform's core prospect, so
    # discovery keeps it by default. Set true to restrict a campaign to businesses
    # that already have a site.
    require_website: bool = False


class CampaignFilterOut(CampaignFilterIn, ORMModel):
    id: uuid.UUID


class CampaignCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    objective: str | None = Field(
        default=None,
        description="Plain-language brief, e.g. 'Find small HVAC businesses in the USA "
        "that need AI automation'.",
    )
    target_prospect_count: int = Field(default=50, ge=1, le=5000)
    budget_usd: float = Field(default=25.0, ge=0)
    offered_services: list[ServiceOffering] = Field(default_factory=list)
    filters: CampaignFilterIn = Field(default_factory=CampaignFilterIn)


class CampaignUpdate(BaseModel):
    name: str | None = None
    objective: str | None = None
    status: CampaignStatus | None = None
    target_prospect_count: int | None = Field(default=None, ge=1, le=5000)
    budget_usd: float | None = Field(default=None, ge=0)
    offered_services: list[ServiceOffering] | None = None
    filters: CampaignFilterIn | None = None


class CampaignOut(ORMModel):
    id: uuid.UUID
    name: str
    objective: str | None
    status: CampaignStatus
    target_prospect_count: int
    budget_usd: float
    spent_usd: float
    offered_services: list[str]
    strategy: dict[str, Any] | None
    filters: CampaignFilterOut | None
    created_at: datetime
    updated_at: datetime


class CampaignStats(BaseModel):
    campaign_id: uuid.UUID
    companies: int
    qualified: int
    ready_to_contact: int
    avg_opportunity_score: float
    total_cost_usd: float
    cost_per_prospect_usd: float


class ResearchJobOut(ORMModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    status: JobStatus
    progress_percent: float
    current_stage: str | None
    plan: dict[str, Any] | None
    companies_discovered: int
    companies_verified: int
    companies_rejected: int
    prospects_qualified: int
    cost_usd: float
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class StartResearchRequest(BaseModel):
    """Body for the one-click START RESEARCH button."""

    max_companies: int | None = Field(default=None, ge=1, le=1000)
    run_inline: bool = Field(
        default=False,
        description="Run synchronously in the API process instead of dispatching to Celery. "
        "Intended for local development and smoke tests.",
    )
