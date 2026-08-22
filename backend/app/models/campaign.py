"""Campaigns, their targeting filters and the research jobs they spawn."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, TimestampMixin, UUIDMixin
from app.models.enums import CampaignStatus, JobStatus


class Campaign(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "campaigns"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # The plain-language brief the user typed, e.g. "Find small HVAC businesses in the USA
    # that need AI automation". The CEO agent turns this into a research strategy.
    objective: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CampaignStatus] = mapped_column(
        String(32), default=CampaignStatus.DRAFT, nullable=False, index=True
    )
    target_prospect_count: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    budget_usd: Mapped[float] = mapped_column(Float, default=25.0, nullable=False)
    spent_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Services we are trying to sell into this segment (list of ServiceOffering values).
    offered_services: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    strategy: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)

    filters: Mapped["CampaignFilter | None"] = relationship(
        back_populates="campaign", uselist=False, cascade="all, delete-orphan"
    )
    jobs: Mapped[list["ResearchJob"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class CampaignFilter(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "campaign_filters"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, unique=True
    )
    countries: Mapped[list[str]] = mapped_column(JSONBType, default=list)  # ISO2 codes
    regions: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    cities: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    industries: Mapped[list[str]] = mapped_column(JSONBType, default=list)  # industry slugs
    business_types: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    exclude_keywords: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    employee_min: Mapped[int | None] = mapped_column(Integer)
    employee_max: Mapped[int | None] = mapped_column(Integer)
    min_opportunity_score: Mapped[float] = mapped_column(Float, default=40.0, nullable=False)
    require_website: Mapped[bool] = mapped_column(default=True, nullable=False)

    campaign: Mapped[Campaign] = relationship(back_populates="filters")


class ResearchJob(UUIDMixin, TimestampMixin, Base):
    """One execution of the AI department against a campaign."""

    __tablename__ = "research_jobs"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[JobStatus] = mapped_column(
        String(32), default=JobStatus.QUEUED, nullable=False, index=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(120), index=True)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(120))
    companies_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    companies_verified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    companies_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prospects_qualified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaign: Mapped[Campaign] = relationship(back_populates="jobs")
