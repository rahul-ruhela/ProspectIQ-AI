"""Companies and everything we learn about them, always with provenance."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, ProvenanceMixin, TimestampMixin, UUIDMixin
from app.models.enums import (
    Certainty,
    ContactStatus,
    EmailQuality,
    EvidenceKind,
    PhoneLineType,
    PipelineStage,
    ScoreCategory,
    SignalType,
    VerificationStatus,
)


class Company(UUIDMixin, TimestampMixin, ProvenanceMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("organization_id", "domain", name="uq_company_org_domain"),
        Index("ix_companies_org_score", "organization_id", "opportunity_score"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    research_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)

    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(300))
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    website: Mapped[str | None] = mapped_column(String(2048))
    description: Mapped[str | None] = mapped_column(Text)
    industry_slug: Mapped[str | None] = mapped_column(String(120), index=True)
    category: Mapped[str | None] = mapped_column(String(160))
    business_type: Mapped[str | None] = mapped_column(String(120))
    employee_count: Mapped[int | None] = mapped_column(Integer)
    employee_range: Mapped[str | None] = mapped_column(String(40))
    founded_year: Mapped[int | None] = mapped_column(Integer)

    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    region: Mapped[str | None] = mapped_column(String(160))
    city: Mapped[str | None] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(String(500))
    postal_code: Mapped[str | None] = mapped_column(String(40))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    phone: Mapped[str | None] = mapped_column(String(60))
    primary_email: Mapped[str | None] = mapped_column(String(320))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    facebook_url: Mapped[str | None] = mapped_column(String(500))

    website_active: Mapped[bool | None] = mapped_column(Boolean)
    is_duplicate_of: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    is_rejected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(400))

    lead_quality_score: Mapped[float | None] = mapped_column(Float)
    opportunity_score: Mapped[float | None] = mapped_column(Float, index=True)
    opportunity_category: Mapped[ScoreCategory | None] = mapped_column(String(32))
    data_completeness: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    last_researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sources: Mapped[list["CompanySource"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    locations: Mapped[list["CompanyLocation"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    website_record: Mapped["Website | None"] = relationship(
        back_populates="company", uselist=False, cascade="all, delete-orphan"
    )
    technologies: Mapped[list["Technology"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    decision_makers: Mapped[list["DecisionMaker"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    signals: Mapped[list["BuyingSignal"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    score: Mapped["OpportunityScore | None"] = relationship(
        back_populates="company", uselist=False, cascade="all, delete-orphan"
    )
    research: Mapped["AIResearch | None"] = relationship(
        back_populates="company", uselist=False, cascade="all, delete-orphan"
    )
    pipeline: Mapped["PipelineEntry | None"] = relationship(
        back_populates="company", uselist=False, cascade="all, delete-orphan"
    )


class CompanySource(UUIDMixin, TimestampMixin, ProvenanceMixin, Base):
    """Each independent place we saw this company. Multiple sources raise confidence."""

    __tablename__ = "company_sources"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    snippet: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)

    company: Mapped[Company] = relationship(back_populates="sources")


class CompanyLocation(UUIDMixin, TimestampMixin, ProvenanceMixin, Base):
    __tablename__ = "company_locations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str | None] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(160))
    region: Mapped[str | None] = mapped_column(String(160))
    country_code: Mapped[str | None] = mapped_column(String(2))
    postal_code: Mapped[str | None] = mapped_column(String(40))
    is_headquarters: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    company: Mapped[Company] = relationship(back_populates="locations")


class Website(UUIDMixin, TimestampMixin, ProvenanceMixin, Base):
    __tablename__ = "websites"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True, unique=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str | None] = mapped_column(String(2048))
    http_status: Mapped[int | None] = mapped_column(Integer)
    is_reachable: Mapped[bool | None] = mapped_column(Boolean)
    is_https: Mapped[bool | None] = mapped_column(Boolean)
    title: Mapped[str | None] = mapped_column(String(500))
    meta_description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(16))
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    load_time_ms: Mapped[int | None] = mapped_column(Integer)
    is_mobile_friendly: Mapped[bool | None] = mapped_column(Boolean)
    copyright_year: Mapped[int | None] = mapped_column(Integer)
    quality_score: Mapped[float | None] = mapped_column(Float)
    crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company] = relationship(back_populates="website_record")
    pages: Mapped[list["WebsitePage"]] = relationship(
        back_populates="website", cascade="all, delete-orphan"
    )
    features: Mapped[list["WebsiteFeature"]] = relationship(
        back_populates="website", cascade="all, delete-orphan"
    )


class WebsitePage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "website_pages"

    website_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    page_type: Mapped[str] = mapped_column(String(60), default="other", nullable=False, index=True)
    http_status: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(500))
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text_excerpt: Mapped[str | None] = mapped_column(Text)
    headings: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    forms_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    website: Mapped[Website] = relationship(back_populates="pages")


class WebsiteFeature(UUIDMixin, TimestampMixin, ProvenanceMixin, Base):
    """A single observed (or missing) capability, e.g. `booking_widget = absent`."""

    __tablename__ = "website_features"

    website_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    feature_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    present: Mapped[bool | None] = mapped_column(Boolean)
    certainty: Mapped[Certainty] = mapped_column(
        String(20), default=Certainty.UNKNOWN, nullable=False
    )
    detail: Mapped[str | None] = mapped_column(String(1000))

    website: Mapped[Website] = relationship(back_populates="features")


class Technology(UUIDMixin, TimestampMixin, ProvenanceMixin, Base):
    __tablename__ = "technologies"
    __table_args__ = (UniqueConstraint("company_id", "slug", name="uq_tech_company_slug"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[str | None] = mapped_column(String(40))
    matched_signature: Mapped[str | None] = mapped_column(String(400))

    company: Mapped[Company] = relationship(back_populates="technologies")


class Contact(UUIDMixin, TimestampMixin, ProvenanceMixin, Base):
    __tablename__ = "contacts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    decision_maker_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("decision_makers.id", ondelete="SET NULL")
    )
    contact_type: Mapped[str] = mapped_column(String(30), nullable=False)  # email | phone
    value: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(120))  # sales, support, owner ...
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    found_on_url: Mapped[str | None] = mapped_column(String(2048))

    company: Mapped[Company] = relationship(back_populates="contacts")
    decision_maker: Mapped["DecisionMaker | None"] = relationship(back_populates="contacts")
    email_verification: Mapped["EmailVerification | None"] = relationship(
        back_populates="contact", uselist=False, cascade="all, delete-orphan"
    )
    phone_verification: Mapped["PhoneVerification | None"] = relationship(
        back_populates="contact", uselist=False, cascade="all, delete-orphan"
    )


class DecisionMaker(UUIDMixin, TimestampMixin, ProvenanceMixin, Base):
    __tablename__ = "decision_makers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(200))
    role_category: Mapped[str | None] = mapped_column(String(60), index=True)
    seniority: Mapped[str | None] = mapped_column(String(40))
    profile_url: Mapped[str | None] = mapped_column(String(1000))
    linkedin_url: Mapped[str | None] = mapped_column(String(1000))
    bio: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="decision_makers")
    contacts: Mapped[list[Contact]] = relationship(back_populates="decision_maker")


class EmailVerification(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "email_verifications"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), index=True, unique=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    syntax_valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    domain_resolves: Mapped[bool | None] = mapped_column(Boolean)
    has_mx: Mapped[bool | None] = mapped_column(Boolean)
    mx_hosts: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    is_disposable: Mapped[bool | None] = mapped_column(Boolean)
    is_free_provider: Mapped[bool | None] = mapped_column(Boolean)
    is_role_account: Mapped[bool | None] = mapped_column(Boolean)
    quality: Mapped[EmailQuality] = mapped_column(
        String(32), default=EmailQuality.UNKNOWN, nullable=False
    )
    status: Mapped[VerificationStatus] = mapped_column(
        String(32), default=VerificationStatus.NEEDS_VERIFICATION, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contact: Mapped[Contact] = relationship(back_populates="email_verification")


class PhoneVerification(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "phone_verifications"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), index=True, unique=True
    )
    raw_value: Mapped[str] = mapped_column(String(60), nullable=False)
    e164: Mapped[str | None] = mapped_column(String(32), index=True)
    country_code: Mapped[str | None] = mapped_column(String(2))
    dial_code: Mapped[str | None] = mapped_column(String(8))
    line_type: Mapped[PhoneLineType] = mapped_column(
        String(32), default=PhoneLineType.UNKNOWN, nullable=False
    )
    carrier: Mapped[str | None] = mapped_column(String(120))
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    whatsapp_likely: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[VerificationStatus] = mapped_column(
        String(32), default=VerificationStatus.NEEDS_VERIFICATION, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contact: Mapped[Contact] = relationship(back_populates="phone_verification")


class CompanyVerification(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "company_verifications"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    exists_confirmed: Mapped[bool | None] = mapped_column(Boolean)
    website_active: Mapped[bool | None] = mapped_column(Boolean)
    industry_match: Mapped[bool | None] = mapped_column(Boolean)
    duplicate_found: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    spam_suspected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    independent_source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[VerificationStatus] = mapped_column(
        String(32), default=VerificationStatus.NEEDS_VERIFICATION, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BuyingSignal(UUIDMixin, TimestampMixin, ProvenanceMixin, Base):
    __tablename__ = "buying_signals"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    signal_type: Mapped[SignalType] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    certainty: Mapped[Certainty] = mapped_column(
        String(20), default=Certainty.POSSIBLE, nullable=False
    )
    strength: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company] = relationship(back_populates="signals")


class OpportunityScore(UUIDMixin, TimestampMixin, Base):
    """Deterministic, fully explainable 0-100 score. Every component is stored."""

    __tablename__ = "opportunity_scores"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True, unique=True
    )
    total: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    category: Mapped[ScoreCategory] = mapped_column(String(32), nullable=False)
    industry_fit: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    company_size: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    website_opportunity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    lead_opportunity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ai_fit: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    technology_readiness: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    buying_signals: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    service_match: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    data_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    recommended_services: Mapped[list[str]] = mapped_column(JSONBType, default=list)

    company: Mapped[Company] = relationship(back_populates="score")


class AIResearch(UUIDMixin, TimestampMixin, Base):
    """The synthesised sales-intelligence report for a company."""

    __tablename__ = "ai_research"

    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True, unique=True
    )
    research_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    what_they_do: Mapped[str | None] = mapped_column(Text)
    how_they_acquire_customers: Mapped[str | None] = mapped_column(Text)
    problems: Mapped[list[dict[str, Any]]] = mapped_column(JSONBType, default=list)
    opportunities: Mapped[list[dict[str, Any]]] = mapped_column(JSONBType, default=list)
    recommended_services: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    why_contact_them: Mapped[str | None] = mapped_column(Text)
    talking_points: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    objections: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    email_draft_subject: Mapped[str | None] = mapped_column(String(300))
    email_draft_body: Mapped[str | None] = mapped_column(Text)
    call_script: Mapped[str | None] = mapped_column(Text)
    # Human approval gate: nothing leaves the platform without this.
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generated_by_model: Mapped[str | None] = mapped_column(String(80))
    generation_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    overall_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    company: Mapped[Company] = relationship(back_populates="research")
    findings: Mapped[list["ResearchFinding"]] = relationship(
        back_populates="research", cascade="all, delete-orphan"
    )


class ResearchFinding(UUIDMixin, TimestampMixin, ProvenanceMixin, Base):
    """One atomic claim inside a report, each tied to evidence."""

    __tablename__ = "research_findings"

    research_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ai_research.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    certainty: Mapped[Certainty] = mapped_column(
        String(20), default=Certainty.UNKNOWN, nullable=False
    )
    impact: Mapped[str | None] = mapped_column(String(40))

    research: Mapped[AIResearch] = relationship(back_populates="findings")
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )


class Evidence(UUIDMixin, TimestampMixin, Base):
    """Raw proof for a finding: the URL, the excerpt and when we saw it."""

    __tablename__ = "evidence"

    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("research_findings.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    kind: Mapped[EvidenceKind] = mapped_column(String(40), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048))
    excerpt: Mapped[str | None] = mapped_column(Text)
    selector: Mapped[str | None] = mapped_column(String(300))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)

    finding: Mapped[ResearchFinding | None] = relationship(back_populates="evidence")


class PipelineEntry(UUIDMixin, TimestampMixin, Base):
    """CRM state for a prospect. One per company."""

    __tablename__ = "pipeline_entries"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True, unique=True
    )
    stage: Mapped[PipelineStage] = mapped_column(
        String(40), default=PipelineStage.DISCOVERED, nullable=False, index=True
    )
    contact_status: Mapped[ContactStatus] = mapped_column(
        String(40), default=ContactStatus.NOT_CONTACTED, nullable=False, index=True
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_action: Mapped[str | None] = mapped_column(String(300))
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    contact_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deal_value_usd: Mapped[float | None] = mapped_column(Float)
    lost_reason: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship(back_populates="pipeline")
    activities: Mapped[list["Activity"]] = relationship(
        back_populates="pipeline_entry", cascade="all, delete-orphan"
    )


class Activity(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "activities"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    pipeline_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pipeline_entries.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    activity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pipeline_entry: Mapped[PipelineEntry | None] = relationship(back_populates="activities")


class HumanFeedback(UUIDMixin, TimestampMixin, Base):
    """Sales-team corrections that feed back into scoring and prompts."""

    __tablename__ = "human_feedback"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    target: Mapped[str] = mapped_column(String(80), nullable=False)  # score | report | contact
    verdict: Mapped[str] = mapped_column(String(40), nullable=False)  # correct | wrong | partial
    corrected_value: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)


class Export(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "exports"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    export_format: Mapped[str] = mapped_column(String(20), default="csv", nullable=False)
    entity: Mapped[str] = mapped_column(String(40), default="companies", nullable=False)
    filters: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
