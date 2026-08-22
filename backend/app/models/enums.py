"""Enumerations shared across models, schemas, agents and the frontend contract."""
from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    RESEARCHER = "researcher"
    SALES_USER = "sales_user"
    VIEWER = "viewer"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class AgentStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PROCESSING = "processing"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    DISABLED = "disabled"


class VerificationStatus(StrEnum):
    """Every fact in the system carries one of these. `UNKNOWN` is a first-class answer."""

    VERIFIED = "verified"
    NEEDS_VERIFICATION = "needs_verification"
    UNKNOWN = "unknown"
    REJECTED = "rejected"


class Certainty(StrEnum):
    """How an inference is allowed to be presented to the user."""

    OBSERVED = "observed"  # directly evidenced on a source we fetched
    LIKELY = "likely"  # strong indirect evidence
    POSSIBLE = "possible"  # weak signal, needs human confirmation
    UNKNOWN = "unknown"  # no evidence at all


class EvidenceKind(StrEnum):
    WEB_PAGE = "web_page"
    SEARCH_RESULT = "search_result"
    DIRECTORY_LISTING = "directory_listing"
    HTTP_HEADER = "http_header"
    DNS_RECORD = "dns_record"
    HTML_SIGNATURE = "html_signature"
    MANUAL = "manual"


class ScoreCategory(StrEnum):
    EXCEPTIONAL = "exceptional"
    HIGH_PRIORITY = "high_priority"
    MEDIUM = "medium"
    LOW = "low"
    POOR = "poor"

    @classmethod
    def from_score(cls, score: float) -> "ScoreCategory":
        if score >= 90:
            return cls.EXCEPTIONAL
        if score >= 75:
            return cls.HIGH_PRIORITY
        if score >= 60:
            return cls.MEDIUM
        if score >= 40:
            return cls.LOW
        return cls.POOR


class PipelineStage(StrEnum):
    DISCOVERED = "discovered"
    RESEARCHING = "researching"
    QUALIFIED = "qualified"
    READY_CONTACT = "ready_contact"
    CONTACTED = "contacted"
    REPLY_RECEIVED = "reply_received"
    MEETING = "meeting"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CUSTOMER = "customer"
    LOST = "lost"


PIPELINE_ORDER: list[PipelineStage] = [
    PipelineStage.DISCOVERED,
    PipelineStage.RESEARCHING,
    PipelineStage.QUALIFIED,
    PipelineStage.READY_CONTACT,
    PipelineStage.CONTACTED,
    PipelineStage.REPLY_RECEIVED,
    PipelineStage.MEETING,
    PipelineStage.PROPOSAL,
    PipelineStage.NEGOTIATION,
    PipelineStage.CUSTOMER,
    PipelineStage.LOST,
]


class ContactStatus(StrEnum):
    NOT_CONTACTED = "not_contacted"
    CALLED = "called"
    CONTACTED = "contacted"
    FOLLOW_UP_REQUIRED = "follow_up_required"
    MEETING_SCHEDULED = "meeting_scheduled"
    NOT_INTERESTED = "not_interested"
    CONVERTED = "converted"


class ActivityType(StrEnum):
    NOTE = "note"
    CALL = "call"
    EMAIL_SENT = "email_sent"
    EMAIL_DRAFTED = "email_drafted"
    MEETING = "meeting"
    STAGE_CHANGE = "stage_change"
    ASSIGNMENT = "assignment"
    SYSTEM = "system"


class EmailQuality(StrEnum):
    BUSINESS = "business"
    PERSONAL = "personal"
    ROLE = "role"  # info@, sales@ ...
    DISPOSABLE = "disposable"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class PhoneLineType(StrEnum):
    FIXED_LINE = "fixed_line"
    MOBILE = "mobile"
    TOLL_FREE = "toll_free"
    VOIP = "voip"
    UNKNOWN = "unknown"


class SignalType(StrEnum):
    HIRING = "hiring"
    GROWTH = "growth"
    NEW_LOCATION = "new_location"
    NEW_SERVICE = "new_service"
    TECH_ADOPTION = "tech_adoption"
    ADVERTISING = "advertising"
    FUNDING = "funding"
    WEBSITE_CHANGE = "website_change"


class ServiceOffering(StrEnum):
    WEBSITE_DEVELOPMENT = "website_development"
    WEBSITE_REDESIGN = "website_redesign"
    CUSTOM_SOFTWARE = "custom_software"
    WEB_APPLICATION = "web_application"
    MOBILE_APPLICATION = "mobile_application"
    AI_AUTOMATION = "ai_automation"
    AI_AGENTS = "ai_agents"
    CRM_SYSTEM = "crm_system"
    MARKETING_AUTOMATION = "marketing_automation"
    LEAD_GENERATION = "lead_generation"
    SUPPORT_AUTOMATION = "support_automation"
    DOCUMENT_AUTOMATION = "document_automation"
    BUSINESS_DASHBOARD = "business_dashboard"
    API_INTEGRATION = "api_integration"


class AgentName(StrEnum):
    CEO_ORCHESTRATOR = "ceo_orchestrator"
    BUSINESS_DISCOVERY = "business_discovery"
    GLOBAL_SEARCH = "global_search"
    WEBSITE_SCRAPING = "website_scraping"
    WEBSITE_INTELLIGENCE = "website_intelligence"
    TECHNOLOGY_DETECTION = "technology_detection"
    AI_OPPORTUNITY = "ai_opportunity"
    DECISION_MAKER = "decision_maker"
    CONTACT_ENRICHMENT = "contact_enrichment"
    EMAIL_VERIFICATION = "email_verification"
    PHONE_INTELLIGENCE = "phone_intelligence"
    BUYING_SIGNAL = "buying_signal"
    COMPANY_VERIFICATION = "company_verification"
    LEAD_QUALITY = "lead_quality"
    OPPORTUNITY_SCORING = "opportunity_scoring"
