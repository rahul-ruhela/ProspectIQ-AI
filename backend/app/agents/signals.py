"""Buying Signal and AI Opportunity agents."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.utils import load_company
from app.agents.website import get_cached_crawl
from app.models.company import BuyingSignal
from app.models.enums import AgentName, Certainty, ServiceOffering, SignalType

# Each pattern is a phrase we must actually find on a fetched page, matched on word
# boundaries. Generic single words ("raised", "doubled", "award-winning") were removed
# after they fired on ordinary marketing copy: a signal that is wrong is worse than a
# signal that is missing, because a salesperson acts on it.
SIGNAL_PATTERNS: dict[SignalType, tuple[tuple[str, float], ...]] = {
    SignalType.HIRING: (
        ("we're hiring", 0.9), ("we are hiring", 0.9), ("now hiring", 0.9),
        ("join our team", 0.7), ("current openings", 0.85), ("job openings", 0.85),
        ("career opportunities", 0.7), ("open positions", 0.85), ("apply today", 0.6),
    ),
    SignalType.GROWTH: (
        ("fastest growing", 0.75), ("growing team", 0.75), ("rapid growth", 0.8),
        ("record year", 0.8), ("expanding our", 0.7), ("we have grown", 0.7),
    ),
    SignalType.NEW_LOCATION: (
        ("new location", 0.9), ("now open in", 0.85), ("second location", 0.9),
        ("new branch", 0.85), ("newest location", 0.9),
    ),
    SignalType.NEW_SERVICE: (
        ("new service", 0.85), ("now offering", 0.85), ("introducing our", 0.75),
        ("recently launched", 0.8), ("newly launched", 0.8), ("new product line", 0.8),
    ),
    SignalType.FUNDING: (
        ("funding round", 0.9), ("series a", 0.9), ("series b", 0.9),
        ("raised funding", 0.9), ("secured investment", 0.85), ("acquired by", 0.8),
        ("private equity", 0.7),
    ),
}

# Pages whose wording routinely trips the patterns without indicating anything about
# the business: policies, terms and cookie notices.
SIGNAL_EXCLUDED_PAGE_TYPES = {"legal", "faq"}


def _find_phrase(haystack: str, phrase: str) -> int:
    """Index of `phrase` in `haystack` on word boundaries, or -1."""
    match = re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", haystack)
    return match.start() if match else -1


# What the presence or absence of a capability makes sellable.
OPPORTUNITY_RULES: tuple[tuple[str, str, ServiceOffering, str], ...] = (
    # (kind, feature_key, service, statement)
    ("missing", "online_booking", ServiceOffering.AI_AUTOMATION,
     "Appointments cannot be booked online, so every booking consumes staff time on the phone."),
    ("missing", "live_chat", ServiceOffering.AI_AGENTS,
     "There is no chat or AI assistant, so out-of-hours enquiries go unanswered."),
    ("missing", "contact_form", ServiceOffering.LEAD_GENERATION,
     "There is no contact form, so website visitors have no low-friction way to enquire."),
    ("missing", "quote_request", ServiceOffering.LEAD_GENERATION,
     "There is no quote request flow, so inbound demand is not captured or measured."),
    ("missing", "customer_portal", ServiceOffering.WEB_APPLICATION,
     "Customers have no self-service portal, so status requests fall to staff."),
    ("missing", "newsletter_signup", ServiceOffering.MARKETING_AUTOMATION,
     "No email capture exists, so traffic cannot be nurtured or retargeted."),
    ("missing", "case_studies", ServiceOffering.WEBSITE_REDESIGN,
     "No case studies or proof of work weakens conversion on higher-value jobs."),
    ("missing", "pricing_published", ServiceOffering.WEBSITE_REDESIGN,
     "No pricing guidance is published, which raises friction for self-serving buyers."),
)


class BuyingSignalAgent(BaseAgent):
    """Detects hiring, growth, expansion, new services, funding and ad activity."""

    key = AgentName.BUYING_SIGNAL
    display_name = "Buying Signal Agent"
    role = "Market Timing Analyst"
    goal = (
        "Detect evidence that a company is growing, hiring, expanding, launching, "
        "advertising or adopting technology - each with the page that showed it."
    )
    tools = ("page_scanner", "careers_analysis", "tech_adoption")
    input_schema = {
        "type": "object",
        "properties": {"company_id": {"type": "string"}},
        "required": ["company_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "signals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "signal_type": {"type": "string"},
                        "title": {"type": "string"},
                        "source_url": {"type": "string"},
                        "strength": {"type": "number"},
                    },
                },
            }
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        company = load_company(ctx, payload)
        if company is None:
            return AgentResult.failure("company_not_found")
        crawl = get_cached_crawl(str(company.id))
        if crawl is None or not crawl.pages:
            return AgentResult(ok=True, data={"signals": []}, confidence=0.0)

        existing = {(s.signal_type, s.title) for s in company.signals}
        detected: list[dict[str, Any]] = []

        pages = [p for p in crawl.pages if p.page_type not in SIGNAL_EXCLUDED_PAGE_TYPES]

        for signal_type, patterns in SIGNAL_PATTERNS.items():
            for page in pages:
                haystack = page.text.lower()
                for phrase, strength in patterns:
                    index = _find_phrase(haystack, phrase)
                    if index < 0:
                        continue
                    excerpt = page.text[max(0, index - 80) : index + 160].strip()
                    title = f'"{phrase}" on the {page.page_type} page'
                    if (signal_type, title) in existing:
                        break
                    existing.add((signal_type, title))
                    company.signals.append(
                        BuyingSignal(
                            signal_type=signal_type,
                            title=title[:400],
                            detail=excerpt[:2000],
                            certainty=Certainty.OBSERVED,
                            strength=strength,
                            source="Company website",
                            source_url=page.url,
                            confidence=strength,
                            verification_status="verified",
                            observed_at=datetime.now(UTC),
                            last_verified_at=datetime.now(UTC),
                        )
                    )
                    detected.append(
                        {
                            "signal_type": str(signal_type),
                            "title": title,
                            "source_url": page.url,
                            "strength": strength,
                            "excerpt": excerpt[:300],
                        }
                    )
                    break
                else:
                    continue
                break

        # A dedicated careers page is itself strong evidence of hiring.
        careers = crawl.page_by_type("careers")
        if careers is not None and not any(d["signal_type"] == str(SignalType.HIRING) for d in detected):
            company.signals.append(
                BuyingSignal(
                    signal_type=SignalType.HIRING,
                    title="Active careers page",
                    detail=f"A careers page is published at {careers.url}.",
                    certainty=Certainty.OBSERVED,
                    strength=0.7,
                    source="Company website",
                    source_url=careers.url,
                    confidence=0.8,
                    verification_status="verified",
                    observed_at=datetime.now(UTC),
                    last_verified_at=datetime.now(UTC),
                )
            )
            detected.append(
                {
                    "signal_type": str(SignalType.HIRING),
                    "title": "Active careers page",
                    "source_url": careers.url,
                    "strength": 0.7,
                }
            )

        # Recent technology adoption: analytics/CRM/booking tooling present at all.
        adopted = [t.name for t in company.technologies if t.category in ("crm", "marketing", "booking", "analytics")]
        if adopted:
            title = "Marketing and sales tooling in use"
            if (SignalType.TECH_ADOPTION, title) not in existing:
                company.signals.append(
                    BuyingSignal(
                        signal_type=SignalType.TECH_ADOPTION,
                        title=title,
                        detail="Detected: " + ", ".join(sorted(adopted)),
                        certainty=Certainty.OBSERVED,
                        strength=0.6,
                        source="Website fingerprint",
                        source_url=company.website,
                        confidence=0.8,
                        verification_status="verified",
                        observed_at=datetime.now(UTC),
                        last_verified_at=datetime.now(UTC),
                    )
                )
                detected.append(
                    {
                        "signal_type": str(SignalType.TECH_ADOPTION),
                        "title": title,
                        "source_url": company.website or "",
                        "strength": 0.6,
                    }
                )

        self.log(ctx, f"Detected {len(detected)} buying signal(s) for {company.name}.")
        return AgentResult(
            ok=True, data={"signals": detected}, confidence=0.8 if detected else 0.4
        )


class AIOpportunityAgent(BaseAgent):
    """Turns observed gaps into classified, evidence-backed opportunities."""

    key = AgentName.AI_OPPORTUNITY
    display_name = "AI Opportunity Agent"
    role = "Solution Strategist"
    goal = (
        "Identify concrete automation and software opportunities from what was actually "
        "observed, labelling each as observed, likely, possible or unknown."
    )
    tools = ("feature_gap_analysis", "service_matcher", "llm_synthesis")
    input_schema = {
        "type": "object",
        "properties": {
            "company_id": {"type": "string"},
            "offered_services": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["company_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "opportunities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "statement": {"type": "string"},
                        "service": {"type": "string"},
                        "certainty": {"type": "string"},
                        "evidence_url": {"type": "string"},
                    },
                },
            },
            "recommended_services": {"type": "array", "items": {"type": "string"}},
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        company = load_company(ctx, payload)
        if company is None:
            return AgentResult.failure("company_not_found")
        website = company.website_record
        if website is None:
            return AgentResult(
                ok=True,
                data={"opportunities": [], "recommended_services": [], "reason": "no_website_data"},
                confidence=0.0,
            )

        offered = set(payload.get("offered_services") or [])
        features = {f.feature_key: f for f in website.features}
        opportunities: list[dict[str, Any]] = []

        for kind, feature_key, service, statement in OPPORTUNITY_RULES:
            feature = features.get(feature_key)
            if feature is None:
                continue
            hit = (kind == "missing" and feature.present is False) or (
                kind == "present" and feature.present is True
            )
            if not hit:
                continue
            if offered and str(service) not in offered:
                continue
            opportunities.append(
                {
                    "statement": statement,
                    "service": str(service),
                    "certainty": str(feature.certainty),
                    "evidence_url": feature.source_url,
                    "feature_key": feature_key,
                }
            )

        # Stack age and quality drive redesign / rebuild recommendations.
        tech_slugs = {t.slug for t in company.technologies}
        year = website.copyright_year
        current_year = datetime.now(UTC).year
        if year and year < current_year - 2 and (not offered or str(ServiceOffering.WEBSITE_REDESIGN) in offered):
            opportunities.append(
                {
                    "statement": f"The site's copyright notice still reads {year}, indicating it has not "
                    "been maintained for at least two years.",
                    "service": str(ServiceOffering.WEBSITE_REDESIGN),
                    "certainty": str(Certainty.OBSERVED),
                    "evidence_url": website.final_url or website.url,
                    "feature_key": "stale_site",
                }
            )
        if website.is_mobile_friendly is False:
            opportunities.append(
                {
                    "statement": "No mobile viewport is declared, so the site is unlikely to work well "
                    "on phones - where most local search traffic originates.",
                    "service": str(ServiceOffering.WEBSITE_REDESIGN),
                    "certainty": str(Certainty.OBSERVED),
                    "evidence_url": website.final_url or website.url,
                    "feature_key": "mobile",
                }
            )
        if not (tech_slugs & {"hubspot", "salesforce", "zoho", "gohighlevel"}):
            opportunities.append(
                {
                    "statement": "No CRM was detected in the page markup, so enquiries are likely tracked "
                    "manually or in a shared inbox.",
                    "service": str(ServiceOffering.CRM_SYSTEM),
                    # We can only see client-side markup: a server-side CRM is invisible to us.
                    "certainty": str(Certainty.LIKELY),
                    "evidence_url": website.final_url or website.url,
                    "feature_key": "crm",
                }
            )
        if tech_slugs & {"google_analytics", "meta_pixel", "google_tag_manager"} and "newsletter_signup" not in features:
            opportunities.append(
                {
                    "statement": "The company pays for tracking and likely for ads, but the site has no "
                    "capture mechanism to convert that traffic.",
                    "service": str(ServiceOffering.MARKETING_AUTOMATION),
                    "certainty": str(Certainty.LIKELY),
                    "evidence_url": website.final_url or website.url,
                    "feature_key": "paid_traffic_leak",
                }
            )

        recommended = _rank_services(opportunities)
        self.log(
            ctx,
            f"Identified {len(opportunities)} opportunity/opportunities for {company.name}; "
            f"top service fit: {recommended[0] if recommended else 'none'}.",
        )
        return AgentResult(
            ok=True,
            data={"opportunities": opportunities, "recommended_services": recommended},
            confidence=0.8 if opportunities else 0.4,
        )


def _rank_services(opportunities: list[dict[str, Any]]) -> list[str]:
    """Order services by how much observed (not assumed) evidence supports them."""
    weights = {"observed": 1.0, "likely": 0.6, "possible": 0.3, "unknown": 0.0}
    scores: dict[str, float] = {}
    for item in opportunities:
        certainty = re.sub(r"^Certainty\.", "", str(item.get("certainty", "unknown"))).lower()
        scores[item["service"]] = scores.get(item["service"], 0.0) + weights.get(certainty, 0.2)
    return [service for service, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]
