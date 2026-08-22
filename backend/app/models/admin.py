"""Admin-configurable providers, connectors, scoring rules and cost tracking."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import JSONBType, TimestampMixin, UUIDMixin


class AIProvider(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ai_providers"

    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AIModel(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ai_models"

    provider_slug: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), default="cheap", nullable=False)
    input_cost_per_mtok: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    output_cost_per_mtok: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class APIKey(UUIDMixin, TimestampMixin, Base):
    """Third-party credentials, encrypted at rest and never returned in clear."""

    __tablename__ = "api_keys"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    provider_slug: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    masked_hint: Mapped[str] = mapped_column(String(60), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Connector(UUIDMixin, TimestampMixin, Base):
    """A discovery/enrichment data source the admin can turn on or off."""

    __tablename__ = "connectors"

    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # search | directory | enrichment
    requires_api_key: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    cost_per_call_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    notes: Mapped[str | None] = mapped_column(Text)


class ScoringRule(UUIDMixin, TimestampMixin, Base):
    """Admin-tunable weights for the opportunity score. Weights must total 100."""

    __tablename__ = "scoring_rules"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    component: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(String(400))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ServiceCatalogItem(UUIDMixin, TimestampMixin, Base):
    """The services we sell, with the signals that indicate a fit."""

    __tablename__ = "service_catalog"

    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    typical_deal_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Website feature keys / signals whose absence or presence indicates a fit.
    trigger_features: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AIUsage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ai_usage"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    research_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    agent_key: Mapped[str | None] = mapped_column(String(80), index=True)
    provider_slug: Mapped[str] = mapped_column(String(60), default="anthropic", nullable=False)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(120))


class CostTracking(UUIDMixin, TimestampMixin, Base):
    """Daily rollup so budget checks never scan the raw usage table."""

    __tablename__ = "cost_tracking"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    llm_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    connector_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    prospects_produced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_per_prospect_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
