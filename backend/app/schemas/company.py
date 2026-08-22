"""Company, prospect and research-report schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import (
    Certainty,
    EmailQuality,
    EvidenceKind,
    PhoneLineType,
    ScoreCategory,
    SignalType,
    VerificationStatus,
)
from app.schemas.common import ORMModel


class TechnologyOut(ORMModel):
    id: uuid.UUID
    slug: str
    name: str
    category: str
    version: str | None
    matched_signature: str | None
    source: str | None
    source_url: str | None
    confidence: float
    verification_status: VerificationStatus
    last_verified_at: datetime | None


class WebsiteFeatureOut(ORMModel):
    id: uuid.UUID
    feature_key: str
    present: bool | None
    certainty: Certainty
    detail: str | None
    source_url: str | None
    confidence: float


class WebsitePageOut(ORMModel):
    id: uuid.UUID
    url: str
    page_type: str
    http_status: int | None
    title: str | None
    word_count: int
    forms_count: int
    fetched_at: datetime | None


class WebsiteOut(ORMModel):
    id: uuid.UUID
    url: str
    final_url: str | None
    http_status: int | None
    is_reachable: bool | None
    is_https: bool | None
    title: str | None
    meta_description: str | None
    pages_crawled: int
    load_time_ms: int | None
    is_mobile_friendly: bool | None
    copyright_year: int | None
    quality_score: float | None
    crawled_at: datetime | None
    features: list[WebsiteFeatureOut] = Field(default_factory=list)
    pages: list[WebsitePageOut] = Field(default_factory=list)


class EmailVerificationOut(ORMModel):
    syntax_valid: bool
    domain_resolves: bool | None
    has_mx: bool | None
    is_disposable: bool | None
    is_free_provider: bool | None
    is_role_account: bool | None
    quality: EmailQuality
    status: VerificationStatus
    confidence: float
    checked_at: datetime | None


class PhoneVerificationOut(ORMModel):
    e164: str | None
    country_code: str | None
    dial_code: str | None
    line_type: PhoneLineType
    is_valid: bool
    whatsapp_likely: bool | None
    status: VerificationStatus
    confidence: float
    checked_at: datetime | None


class ContactOut(ORMModel):
    id: uuid.UUID
    contact_type: str
    value: str
    label: str | None
    is_primary: bool
    found_on_url: str | None
    source: str | None
    source_url: str | None
    confidence: float
    verification_status: VerificationStatus
    last_verified_at: datetime | None
    email_verification: EmailVerificationOut | None = None
    phone_verification: PhoneVerificationOut | None = None


class DecisionMakerOut(ORMModel):
    id: uuid.UUID
    full_name: str
    role_title: str | None
    role_category: str | None
    seniority: str | None
    profile_url: str | None
    linkedin_url: str | None
    source: str | None
    source_url: str | None
    confidence: float
    verification_status: VerificationStatus
    contacts: list[ContactOut] = Field(default_factory=list)


class BuyingSignalOut(ORMModel):
    id: uuid.UUID
    signal_type: SignalType
    title: str
    detail: str | None
    certainty: Certainty
    strength: float
    source_url: str | None
    confidence: float
    observed_at: datetime | None


class OpportunityScoreOut(ORMModel):
    total: float
    category: ScoreCategory
    industry_fit: float
    company_size: float
    website_opportunity: float
    lead_opportunity: float
    ai_fit: float
    technology_readiness: float
    buying_signals: float
    service_match: float
    data_confidence: float
    breakdown: dict[str, Any] | None
    recommended_services: list[str]


class EvidenceOut(ORMModel):
    id: uuid.UUID
    kind: EvidenceKind
    url: str | None
    excerpt: str | None
    observed_at: datetime | None


class ResearchFindingOut(ORMModel):
    id: uuid.UUID
    category: str
    statement: str
    certainty: Certainty
    impact: str | None
    confidence: float
    source_url: str | None
    evidence: list[EvidenceOut] = Field(default_factory=list)


class AIResearchOut(ORMModel):
    id: uuid.UUID
    summary: str | None
    what_they_do: str | None
    how_they_acquire_customers: str | None
    problems: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]
    recommended_services: list[str]
    why_contact_them: str | None
    talking_points: list[str]
    objections: list[str]
    email_draft_subject: str | None
    email_draft_body: str | None
    call_script: str | None
    approved_at: datetime | None
    generated_by_model: str | None
    overall_confidence: float
    findings: list[ResearchFindingOut] = Field(default_factory=list)


class CompanySourceOut(ORMModel):
    id: uuid.UUID
    source_type: str
    title: str | None
    snippet: str | None
    source_url: str | None
    confidence: float


class CompanyListItem(ORMModel):
    id: uuid.UUID
    name: str
    domain: str | None
    website: str | None
    industry_slug: str | None
    country_code: str | None
    city: str | None
    employee_count: int | None
    opportunity_score: float | None
    opportunity_category: ScoreCategory | None
    lead_quality_score: float | None
    data_completeness: float
    verification_status: VerificationStatus
    is_rejected: bool
    last_researched_at: datetime | None
    created_at: datetime


class CompanyDetail(CompanyListItem):
    legal_name: str | None
    description: str | None
    category: str | None
    business_type: str | None
    employee_range: str | None
    founded_year: int | None
    region: str | None
    address: str | None
    postal_code: str | None
    phone: str | None
    primary_email: str | None
    linkedin_url: str | None
    website_active: bool | None
    rejection_reason: str | None
    confidence: float
    source: str | None
    source_url: str | None
    sources: list[CompanySourceOut] = Field(default_factory=list)
    website_record: WebsiteOut | None = None
    technologies: list[TechnologyOut] = Field(default_factory=list)
    contacts: list[ContactOut] = Field(default_factory=list)
    decision_makers: list[DecisionMakerOut] = Field(default_factory=list)
    signals: list[BuyingSignalOut] = Field(default_factory=list)
    score: OpportunityScoreOut | None = None
    research: AIResearchOut | None = None


class CompanyFilterParams(BaseModel):
    q: str | None = None
    campaign_id: uuid.UUID | None = None
    country_code: str | None = None
    industry_slug: str | None = None
    min_score: float | None = Field(default=None, ge=0, le=100)
    max_score: float | None = Field(default=None, ge=0, le=100)
    category: ScoreCategory | None = None
    include_rejected: bool = False
    has_contact: bool | None = None
    sort_by: str = Field(default="opportunity_score")
    sort_dir: str = Field(default="desc", pattern="^(asc|desc)$")


class ApproveReportRequest(BaseModel):
    approved: bool = True
    note: str | None = None
