"""Builds the sales-intelligence report for a company.

The report is assembled from observed facts first. The LLM is used only to phrase what
was already established — it is given the crawled text and the structured findings and
is told explicitly to answer "Unknown" rather than fill gaps. Every narrative claim is
mirrored by a :class:`ResearchFinding` with its own evidence row.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.agents.base import AgentContext
from app.agents.website import get_cached_crawl
from app.core.logging import get_logger
from app.llm.client import SMART
from app.models.company import AIResearch, Company, Evidence, ResearchFinding
from app.models.enums import Certainty, EvidenceKind, ScoreCategory, VerificationStatus
from app.scraper.extract import summarise_site_text

logger = get_logger(__name__)

REPORT_SYSTEM = """You are a B2B sales analyst preparing a human salesperson for a first \
conversation with a company. You are given ONLY verified observations gathered from the \
company's own website and from search results.

Absolute rules:
1. Never state anything that is not supported by the observations you are given.
2. If something is not in the observations, write exactly "Unknown" - never guess a name, \
an email, a phone number, a revenue figure, a headcount or a technology.
3. Distinguish what was observed from what is inferred. Inferences must be phrased as \
inferences ("the site shows no booking widget, which suggests...").
4. Never write an email that claims knowledge you do not have.
5. Be concrete and specific. A salesperson must be able to open the call with it.
"""

REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string", "description": "Three to five sentences on who this company is."},
        "what_they_do": {"type": "string"},
        "how_they_acquire_customers": {
            "type": "string",
            "description": "Based only on observed channels; use 'Unknown' when unclear.",
        },
        "problems": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "statement": {"type": "string"},
                    "certainty": {"type": "string", "enum": ["observed", "likely", "possible", "unknown"]},
                    "evidence_url": {"type": "string"},
                },
                "required": ["statement", "certainty", "evidence_url"],
            },
        },
        "why_contact_them": {"type": "string"},
        "talking_points": {"type": "array", "items": {"type": "string"}},
        "objections": {"type": "array", "items": {"type": "string"}},
        "email_subject": {"type": "string"},
        "email_body": {"type": "string"},
        "call_opening": {"type": "string"},
    },
    "required": [
        "summary", "what_they_do", "how_they_acquire_customers", "problems",
        "why_contact_them", "talking_points", "objections", "email_subject",
        "email_body", "call_opening",
    ],
}


def build_report(
    ctx: AgentContext,
    company: Company,
    *,
    opportunities: list[dict[str, Any]],
    weaknesses: list[str],
    use_llm: bool = True,
) -> AIResearch:
    """Create or refresh the company's AI research report."""
    db: Session = ctx.db
    research = company.research or AIResearch(company_id=company.id)
    research.research_job_id = ctx.research_job_id

    observations = _collect_observations(company, weaknesses, opportunities)
    findings = _build_findings(company, opportunities, weaknesses)

    # Deterministic baseline: always present, even with no LLM configured.
    research.summary = _deterministic_summary(company, observations)
    research.what_they_do = company.description or (
        company.website_record.meta_description if company.website_record else None
    ) or "Unknown"
    research.how_they_acquire_customers = _acquisition_summary(company)
    research.problems = [
        {"statement": f.statement, "certainty": str(f.certainty), "evidence_url": f.source_url}
        for f in findings
        if f.category == "problem"
    ]
    research.opportunities = opportunities
    research.recommended_services = (
        company.score.recommended_services if company.score else []
    )
    research.why_contact_them = _why_contact(company, opportunities)
    research.talking_points = _talking_points(company, opportunities, weaknesses)
    research.objections = _objections(company)
    research.overall_confidence = round(
        (company.confidence + (company.data_completeness or 0.0)) / 2, 3
    )

    llm_used = False
    if use_llm and ctx.llm.available and _worth_llm_spend(company):
        payload = _llm_payload(company, observations, opportunities, weaknesses)
        result = ctx.llm.structured(
            system=REPORT_SYSTEM,
            prompt=payload,
            schema=REPORT_SCHEMA,
            tool_name="sales_intelligence_report",
            tool_description="Record the grounded sales-intelligence report for this company.",
            tier=SMART,
            # The report schema is a handful of short fields; 4096 only ever bought
            # unused headroom, and on a metered free tier headroom is the cost.
            max_tokens=1536,
        )
        ctx.record_llm(result, "ai_report", "company_report")
        research.generation_cost_usd = result.cost_usd
        research.generated_by_model = result.model
        if result.ok and result.data:
            data = result.data
            research.summary = data.get("summary") or research.summary
            research.what_they_do = data.get("what_they_do") or research.what_they_do
            research.how_they_acquire_customers = (
                data.get("how_they_acquire_customers") or research.how_they_acquire_customers
            )
            if data.get("problems"):
                research.problems = data["problems"]
            research.why_contact_them = data.get("why_contact_them") or research.why_contact_them
            research.talking_points = data.get("talking_points") or research.talking_points
            research.objections = data.get("objections") or research.objections
            research.email_draft_subject = (data.get("email_subject") or "")[:300] or None
            research.email_draft_body = data.get("email_body") or None
            research.call_script = data.get("call_opening") or None
            llm_used = True
        else:
            logger.warning("report_llm_failed", company=str(company.id), error=result.error)

    if not llm_used:
        subject, body = _deterministic_email(company, opportunities)
        research.email_draft_subject = subject
        research.email_draft_body = body
        research.call_script = _deterministic_call_script(company, opportunities)
        research.generated_by_model = research.generated_by_model or "rules_engine"

    if company.research is None:
        company.research = research
    db.flush()

    # Findings are rebuilt each run so the report always matches the current crawl.
    for existing in list(research.findings):
        db.delete(existing)
    db.flush()
    for finding in findings:
        finding.research_id = research.id
        finding.company_id = company.id
        research.findings.append(finding)
    db.flush()
    return research


# --- observation assembly -------------------------------------------------------


def _collect_observations(
    company: Company, weaknesses: list[str], opportunities: list[dict[str, Any]]
) -> dict[str, Any]:
    website = company.website_record
    return {
        "name": company.name,
        "domain": company.domain,
        "website": company.website,
        "country": company.country_code,
        "city": company.city,
        "industry": company.industry_slug,
        "employee_count": company.employee_count,
        "website_reachable": bool(website and website.is_reachable),
        "website_quality_score": website.quality_score if website else None,
        "https": website.is_https if website else None,
        "mobile_friendly": website.is_mobile_friendly if website else None,
        "copyright_year": website.copyright_year if website else None,
        "pages_crawled": [
            {"type": p.page_type, "url": p.url} for p in (website.pages if website else [])
        ],
        "present_capabilities": [
            f.feature_key for f in (website.features if website else []) if f.present
        ],
        "absent_capabilities": [
            f.feature_key for f in (website.features if website else []) if f.present is False
        ],
        "technologies": [
            {"name": t.name, "category": t.category, "evidence": t.matched_signature}
            for t in company.technologies
        ],
        "decision_makers": [
            {"name": d.full_name, "role": d.role_title, "source": d.source_url}
            for d in company.decision_makers
        ],
        "contacts": [
            {
                "type": c.contact_type,
                "value": c.value,
                "status": str(c.verification_status),
                "source": c.source_url,
            }
            for c in company.contacts
        ],
        "buying_signals": [
            {"type": str(s.signal_type), "title": s.title, "detail": s.detail, "source": s.source_url}
            for s in company.signals
        ],
        "website_weaknesses": weaknesses,
        "opportunities": opportunities,
        "opportunity_score": company.opportunity_score,
        "sources": [
            {"type": s.source_type, "title": s.title, "url": s.source_url} for s in company.sources
        ],
    }


def _build_findings(
    company: Company, opportunities: list[dict[str, Any]], weaknesses: list[str]
) -> list[ResearchFinding]:
    findings: list[ResearchFinding] = []
    website = company.website_record
    base_url = (website.final_url or website.url) if website else company.website

    def add(category: str, statement: str, certainty: Certainty, url: str | None, impact: str, excerpt: str = "") -> None:
        finding = ResearchFinding(
            category=category,
            statement=statement[:4000],
            certainty=certainty,
            impact=impact,
            source="ProspectIQ analysis",
            source_url=url,
            confidence=0.9 if certainty == Certainty.OBSERVED else 0.6,
            verification_status=VerificationStatus.VERIFIED,
            last_verified_at=datetime.now(UTC),
        )
        finding.evidence.append(
            Evidence(
                company_id=company.id,
                kind=EvidenceKind.WEB_PAGE if url else EvidenceKind.MANUAL,
                url=url,
                excerpt=excerpt[:2000] or statement[:500],
                observed_at=datetime.now(UTC),
            )
        )
        findings.append(finding)

    if website and website.is_reachable:
        add(
            "identity",
            f"{company.name} operates a live website at {base_url}"
            + (f", built with {', '.join(t.name for t in company.technologies[:3])}" if company.technologies else "")
            + ".",
            Certainty.OBSERVED,
            base_url,
            "context",
        )
    for opportunity in opportunities:
        certainty_raw = str(opportunity.get("certainty", "possible")).split(".")[-1].lower()
        try:
            certainty = Certainty(certainty_raw)
        except ValueError:
            certainty = Certainty.POSSIBLE
        add(
            "problem",
            opportunity["statement"],
            certainty,
            opportunity.get("evidence_url") or base_url,
            "revenue",
        )
    for weakness in weaknesses[:6]:
        add("website_quality", weakness, Certainty.OBSERVED, base_url, "conversion")
    for signal in company.signals[:5]:
        add(
            "buying_signal",
            f"{signal.title}: {(signal.detail or '')[:200]}",
            signal.certainty,
            signal.source_url,
            "timing",
            signal.detail or "",
        )
    for dm in company.decision_makers[:5]:
        add(
            "decision_maker",
            f"{dm.full_name} is listed as {dm.role_title or 'a decision maker'}.",
            Certainty.OBSERVED,
            dm.source_url,
            "access",
        )
    if not company.decision_makers:
        add(
            "decision_maker",
            "No decision maker is named anywhere on the company's public pages. "
            "This must be established by a human before outreach.",
            Certainty.UNKNOWN,
            base_url,
            "access",
        )
    return findings


# --- deterministic narrative (used with or without an LLM) ----------------------


def _deterministic_summary(company: Company, obs: dict[str, Any]) -> str:
    parts: list[str] = [company.name]
    if company.industry_slug:
        parts.append(f"operates in {company.industry_slug.replace('_', ' ')}")
    location = ", ".join(p for p in (company.city, company.country_code) if p)
    if location:
        parts.append(f"based in {location}")
    sentence = " ".join(parts) + "."
    if obs["website_reachable"]:
        sentence += (
            f" Its website scored {obs['website_quality_score']:.0f}/100 on our quality assessment"
            f" across {len(obs['pages_crawled'])} pages reviewed."
        )
    else:
        sentence += " Its website could not be reached during research."
    if obs["technologies"]:
        sentence += " Stack detected: " + ", ".join(t["name"] for t in obs["technologies"][:5]) + "."
    if not company.decision_makers:
        sentence += " No decision maker is publicly named - this is Unknown and needs verification."
    return sentence


def _acquisition_summary(company: Company) -> str:
    channels: list[str] = []
    tech = {t.slug for t in company.technologies}
    website = company.website_record
    features = {f.feature_key for f in (website.features if website else []) if f.present}
    if tech & {"google_analytics", "google_tag_manager"}:
        channels.append("measures web traffic with Google analytics tooling")
    if tech & {"meta_pixel", "linkedin_insight", "tiktok_pixel"}:
        channels.append("runs paid social tracking pixels, indicating advertising spend")
    if "blog" in features:
        channels.append("publishes content on a blog")
    if "newsletter_signup" in features:
        channels.append("collects email subscribers")
    if "online_booking" in features:
        channels.append("takes bookings online")
    if "contact_form" in features:
        channels.append("captures enquiries through a web form")
    if company.phone and "contact_form" not in features:
        channels.append("relies on inbound phone calls")
    if not channels:
        return "Unknown - no acquisition channel could be observed on the pages we reviewed."
    return f"{company.name} " + "; ".join(channels) + "."


def _why_contact(company: Company, opportunities: list[dict[str, Any]]) -> str:
    if not opportunities:
        return (
            "No specific gap was observed. Contact only if the vertical or location is "
            "strategically valuable; otherwise deprioritise."
        )
    top = opportunities[0]
    category = company.opportunity_category or ScoreCategory.MEDIUM
    return (
        f"Scored {company.opportunity_score:.0f}/100 ({str(category).replace('_', ' ')}). "
        f"The clearest opening is: {top['statement']} "
        f"Evidence: {top.get('evidence_url') or company.website}."
    )


def _talking_points(
    company: Company, opportunities: list[dict[str, Any]], weaknesses: list[str]
) -> list[str]:
    points = [o["statement"] for o in opportunities[:4]]
    points.extend(weaknesses[: max(0, 5 - len(points))])
    for signal in company.signals[:2]:
        points.append(f"Timing: {signal.title}. {(signal.detail or '')[:120]}")
    return points[:6]


def _objections(company: Company) -> list[str]:
    objections = [
        "\"We already have someone who handles our website.\" - ask who, and when it was last updated.",
        "\"We get all our work from referrals.\" - ask what happens to the enquiries that arrive at 9pm.",
    ]
    tech = {t.slug for t in company.technologies}
    if tech & {"wix", "squarespace", "godaddy_builder"}:
        objections.append(
            "\"Our site works fine.\" - the current builder limits automation and integrations."
        )
    if tech & {"hubspot", "salesforce", "zoho"}:
        objections.append(
            "\"We already pay for a CRM.\" - position the work as making that CRM actually used."
        )
    return objections


def _deterministic_email(company: Company, opportunities: list[dict[str, Any]]) -> tuple[str, str]:
    """A conservative draft that only references what we observed. Never auto-sent."""
    contact_name = company.decision_makers[0].full_name.split()[0] if company.decision_makers else "there"
    top = opportunities[0]["statement"] if opportunities else ""
    subject = f"Quick note about {company.domain or company.name}"
    body_lines = [
        f"Hi {contact_name},",
        "",
        f"I was looking at {company.website or company.name} and noticed something specific.",
    ]
    if top:
        body_lines += ["", top]
    body_lines += [
        "",
        "We build the kind of thing that closes that gap - usually in a couple of weeks, "
        "and we can show you comparable work before you commit to anything.",
        "",
        "Worth a 15 minute call this week?",
        "",
        "[YOUR NAME]",
        "",
        "-- DRAFT: reviewed and approved by a human before sending. --",
    ]
    return subject, "\n".join(body_lines)


def _deterministic_call_script(company: Company, opportunities: list[dict[str, Any]]) -> str:
    opener = opportunities[0]["statement"] if opportunities else "I wanted to understand how you handle enquiries."
    return (
        f"Opening: \"Hi, is this {company.name}? I'll be quick - I was looking at your site and "
        f"noticed one thing. {opener} Is that something you have handled another way, or is it "
        "actually a gap?\"\n\n"
        "Then: listen. Do not pitch until they describe the current process."
    )


# --- helpers --------------------------------------------------------------------


def _worth_llm_spend(company: Company) -> bool:
    """Only spend the expensive model on prospects that already look qualified."""
    return (company.opportunity_score or 0) >= 60 and not company.is_rejected


def _llm_payload(
    company: Company,
    observations: dict[str, Any],
    opportunities: list[dict[str, Any]],
    weaknesses: list[str],
) -> str:
    crawl = get_cached_crawl(str(company.id))
    site_text = summarise_site_text(crawl.pages, limit=6000) if crawl else ""
    return (
        "VERIFIED OBSERVATIONS (JSON):\n"
        + json.dumps(observations, indent=2, default=str)[:12000]
        + "\n\nTEXT ACTUALLY FETCHED FROM THE COMPANY WEBSITE:\n"
        + (site_text or "(no page text was retrieved)")
        + "\n\nWrite the sales-intelligence report. Every claim must trace to the data above. "
        "Where the data does not answer a field, write \"Unknown\"."
    )
