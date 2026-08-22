"""Administration schemas: providers, keys, connectors, scoring, catalogue."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AIProviderOut(ORMModel):
    id: uuid.UUID
    slug: str
    name: str
    base_url: str | None
    is_enabled: bool


class AIModelOut(ORMModel):
    id: uuid.UUID
    provider_slug: str
    model_id: str
    display_name: str
    tier: str
    input_cost_per_mtok: float
    output_cost_per_mtok: float
    max_output_tokens: int
    is_enabled: bool


class AIModelUpdate(BaseModel):
    tier: str | None = Field(default=None, pattern="^(cheap|smart)$")
    input_cost_per_mtok: float | None = Field(default=None, ge=0)
    output_cost_per_mtok: float | None = Field(default=None, ge=0)
    is_enabled: bool | None = None


class APIKeyCreate(BaseModel):
    provider_slug: str
    label: str
    value: str = Field(min_length=8, repr=False)


class APIKeyOut(ORMModel):
    id: uuid.UUID
    provider_slug: str
    label: str
    masked_hint: str
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


class ConnectorOut(ORMModel):
    id: uuid.UUID
    slug: str
    name: str
    kind: str
    requires_api_key: bool
    is_enabled: bool
    rate_limit_per_minute: int
    cost_per_call_usd: float
    notes: str | None


class ConnectorUpdate(BaseModel):
    is_enabled: bool | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=600)
    cost_per_call_usd: float | None = Field(default=None, ge=0)


class ConnectorHealth(BaseModel):
    slug: str
    name: str
    available: bool
    reason: str


class ScoringRuleOut(ORMModel):
    id: uuid.UUID
    component: str
    weight: float
    description: str | None
    is_active: bool


class ScoringRuleUpdate(BaseModel):
    weight: float = Field(ge=0, le=100)
    is_active: bool | None = None


class ServiceCatalogOut(ORMModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    typical_deal_usd: float
    trigger_features: list[str]
    is_active: bool


class IndustryOut(ORMModel):
    id: uuid.UUID
    slug: str
    name: str
    naics_code: str | None
    ai_fit_baseline: float
    is_active: bool


class CountryOut(ORMModel):
    id: uuid.UUID
    iso2: str
    iso3: str
    name: str
    continent: str
    phone_code: str | None
    is_supported: bool


class CostSummary(BaseModel):
    period_days: int
    llm_cost_usd: float
    connector_cost_usd: float
    total_cost_usd: float
    prospects_produced: int
    cost_per_prospect_usd: float
    by_model: list[dict[str, float | str | int]]
    by_agent: list[dict[str, float | str | int]]
