"""Deterministic, explainable opportunity scoring.

The score is a weighted sum of nine components, each normalised to 0-1 and each
accompanied by the reasons that produced it. Weights default to the product spec and
can be re-tuned per organisation in the admin panel (``scoring_rules``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin import ScoringRule
from app.models.company import Company
from app.models.enums import ScoreCategory, ServiceOffering
from app.models.geo import Industry

DEFAULT_WEIGHTS: dict[str, float] = {
    "industry_fit": 15.0,
    "company_size": 10.0,
    "website_opportunity": 10.0,
    "lead_opportunity": 15.0,
    "ai_fit": 15.0,
    "technology_readiness": 10.0,
    "buying_signals": 10.0,
    "service_match": 10.0,
    "data_confidence": 5.0,
}

WEIGHT_DESCRIPTIONS: dict[str, str] = {
    "industry_fit": "How well the vertical matches the services we sell.",
    "company_size": "Whether the company is big enough to buy and small enough to reach.",
    "website_opportunity": "How much room the current website leaves for improvement.",
    "lead_opportunity": "Gaps in how the company captures and converts demand.",
    "ai_fit": "How suitable the business model is for AI automation.",
    "technology_readiness": "Whether the company already buys and adopts software.",
    "buying_signals": "Evidence the company is growing, hiring or launching now.",
    "service_match": "Strength of the match to a specific service we offer.",
    "data_confidence": "How well verified our data about the company is.",
}

# Employee bands that historically convert best for agency-style services.
SIZE_CURVE: tuple[tuple[int, int, float], ...] = (
    (1, 4, 0.45),
    (5, 19, 0.85),
    (20, 99, 1.0),
    (100, 249, 0.75),
    (250, 999, 0.5),
    (1000, 10_000_000, 0.25),
)


@dataclass(slots=True)
class ComponentScore:
    key: str
    normalised: float
    weight: float
    reasons: list[str] = field(default_factory=list)

    @property
    def points(self) -> float:
        return round(self.normalised * self.weight, 2)


@dataclass(slots=True)
class ScoreOutcome:
    total: float
    category: ScoreCategory
    components: dict[str, ComponentScore]
    recommended_services: list[str]

    def breakdown(self) -> dict[str, Any]:
        return {
            key: {
                "normalised": round(component.normalised, 3),
                "weight": component.weight,
                "points": component.points,
                "reasons": component.reasons,
            }
            for key, component in self.components.items()
        }


def load_weights(db: Session, organization_id: Any | None = None) -> dict[str, float]:
    rows = (
        db.execute(select(ScoringRule).where(ScoringRule.is_active.is_(True)))
        .scalars()
        .all()
    )
    if not rows:
        return dict(DEFAULT_WEIGHTS)
    scoped = [r for r in rows if r.organization_id == organization_id] or [
        r for r in rows if r.organization_id is None
    ]
    weights = dict(DEFAULT_WEIGHTS)
    for rule in scoped:
        if rule.component in weights:
            weights[rule.component] = rule.weight
    return weights


def score_company(
    db: Session,
    company: Company,
    *,
    offered_services: list[str] | None = None,
    opportunities: list[dict[str, Any]] | None = None,
) -> ScoreOutcome:
    weights = load_weights(db, company.organization_id)
    offered = set(offered_services or [])
    opportunities = opportunities or []

    website = company.website_record
    features = {f.feature_key: f for f in website.features} if website else {}
    tech_slugs = {t.slug for t in company.technologies}
    tech_categories = {t.category for t in company.technologies}

    components: dict[str, ComponentScore] = {}

    # --- industry fit ---
    reasons: list[str] = []
    industry_value = 0.5
    if company.industry_slug:
        industry = db.execute(
            select(Industry).where(Industry.slug == company.industry_slug)
        ).scalar_one_or_none()
        if industry is not None:
            industry_value = industry.ai_fit_baseline
            reasons.append(f"{industry.name} has a baseline fit of {industry.ai_fit_baseline:.2f}.")
        else:
            reasons.append(f"Industry '{company.industry_slug}' is not in the catalogue; using neutral fit.")
    else:
        reasons.append("Industry unknown; using neutral fit.")
    components["industry_fit"] = ComponentScore("industry_fit", industry_value, weights["industry_fit"], reasons)

    # --- company size ---
    reasons = []
    size_value = 0.5
    if company.employee_count:
        for low, high, value in SIZE_CURVE:
            if low <= company.employee_count <= high:
                size_value = value
                reasons.append(f"{company.employee_count} employees falls in the {low}-{high} band.")
                break
    else:
        reasons.append("Employee count unknown; scored neutrally rather than assumed.")
    components["company_size"] = ComponentScore("company_size", size_value, weights["company_size"], reasons)

    # --- website opportunity (inverse of quality) ---
    reasons = []
    if website and website.quality_score is not None:
        website_value = max(0.0, min(1.0, (100.0 - website.quality_score) / 100.0))
        reasons.append(f"Website quality scored {website.quality_score:.0f}/100, leaving room to improve.")
    elif website and website.is_reachable is False:
        website_value = 0.2
        reasons.append("Website is unreachable, so there is nothing to improve yet.")
    else:
        website_value = 0.3
        reasons.append("No website analysis available.")
    components["website_opportunity"] = ComponentScore(
        "website_opportunity", website_value, weights["website_opportunity"], reasons
    )

    # --- lead opportunity ---
    reasons = []
    lead_gaps = [
        key
        for key in ("contact_form", "quote_request", "newsletter_signup", "live_chat", "online_booking")
        if key in features and features[key].present is False
    ]
    lead_value = min(1.0, len(lead_gaps) / 4.0) if features else 0.3
    if lead_gaps:
        reasons.append("Missing lead capture: " + ", ".join(g.replace("_", " ") for g in lead_gaps) + ".")
    elif features:
        reasons.append("Lead capture is already in place; less room to sell here.")
    else:
        reasons.append("No website features analysed.")
    components["lead_opportunity"] = ComponentScore(
        "lead_opportunity", lead_value, weights["lead_opportunity"], reasons
    )

    # --- AI fit ---
    reasons = []
    ai_value = industry_value * 0.5
    manual_indicators = [
        key
        for key in ("online_booking", "live_chat", "customer_portal")
        if key in features and features[key].present is False
    ]
    if manual_indicators:
        ai_value += min(0.5, 0.18 * len(manual_indicators))
        reasons.append(
            "Manual workflows implied by missing: "
            + ", ".join(m.replace("_", " ") for m in manual_indicators)
            + "."
        )
    if features.get("emergency_service") and features["emergency_service"].present:
        ai_value = min(1.0, ai_value + 0.1)
        reasons.append("Advertises 24/7 availability, which after-hours AI handling directly supports.")
    if not reasons:
        reasons.append("No automation gaps observed.")
    components["ai_fit"] = ComponentScore("ai_fit", min(1.0, ai_value), weights["ai_fit"], reasons)

    # --- technology readiness ---
    reasons = []
    readiness = 0.0
    if tech_categories & {"crm", "marketing"}:
        readiness += 0.4
        reasons.append("Already runs CRM or marketing tooling.")
    if tech_categories & {"analytics", "advertising"}:
        readiness += 0.3
        reasons.append("Runs analytics or ad tracking, so measurement is already valued.")
    if tech_categories & {"payments", "booking"}:
        readiness += 0.2
        reasons.append("Transacts or schedules online already.")
    if tech_slugs & {"react", "nextjs", "vue", "angular", "webflow"}:
        readiness += 0.1
        reasons.append("Modern frontend stack indicates recent investment.")
    if not reasons:
        reasons.append("No commercial software detected in page markup.")
        readiness = 0.15
    components["technology_readiness"] = ComponentScore(
        "technology_readiness", min(1.0, readiness), weights["technology_readiness"], reasons
    )

    # --- buying signals ---
    reasons = []
    signal_value = 0.0
    if company.signals:
        # Recent, strong, corroborated signals matter more than the raw count.
        strengths = sorted((s.strength for s in company.signals), reverse=True)[:4]
        signal_value = min(1.0, sum(strengths) / 3.0)
        reasons.extend(f"{s.title} ({s.strength:.2f})" for s in company.signals[:4])
    else:
        reasons.append("No buying signals observed.")
    components["buying_signals"] = ComponentScore(
        "buying_signals", signal_value, weights["buying_signals"], reasons
    )

    # --- service match ---
    reasons = []
    matched_services = {o["service"] for o in opportunities if o.get("service")}
    if offered:
        overlap = matched_services & offered
        match_value = min(1.0, len(overlap) / max(1, min(3, len(offered))))
        if overlap:
            reasons.append("Direct fit for: " + ", ".join(sorted(_pretty(s) for s in overlap)) + ".")
        else:
            reasons.append("No overlap between observed gaps and the services this campaign sells.")
    else:
        match_value = min(1.0, len(matched_services) / 3.0)
        reasons.append(
            "Opportunities found for: " + ", ".join(sorted(_pretty(s) for s in matched_services))
            if matched_services
            else "No specific service opportunity identified."
        )
    components["service_match"] = ComponentScore(
        "service_match", match_value, weights["service_match"], reasons
    )

    # --- data confidence ---
    reasons = []
    confidence_inputs: list[float] = [company.confidence]
    if len(company.sources) > 1:
        confidence_inputs.append(0.9)
        reasons.append(f"Corroborated by {len(company.sources)} independent sources.")
    if website and website.is_reachable:
        confidence_inputs.append(0.95)
        reasons.append("Website was fetched successfully.")
    verified_contacts = [
        c for c in company.contacts if c.verification_status == "verified"
    ]
    if verified_contacts:
        confidence_inputs.append(0.9)
        reasons.append(f"{len(verified_contacts)} verified contact(s).")
    if company.decision_makers:
        confidence_inputs.append(0.85)
        reasons.append(f"{len(company.decision_makers)} named decision maker(s).")
    data_value = sum(confidence_inputs) / len(confidence_inputs)
    if not reasons:
        reasons.append("Single unverified source only.")
    components["data_confidence"] = ComponentScore(
        "data_confidence", min(1.0, data_value), weights["data_confidence"], reasons
    )

    total = round(sum(c.points for c in components.values()), 2)
    recommended = _recommended_services(opportunities, offered)
    return ScoreOutcome(
        total=total,
        category=ScoreCategory.from_score(total),
        components=components,
        recommended_services=recommended,
    )


def _recommended_services(opportunities: list[dict[str, Any]], offered: set[str]) -> list[str]:
    weights = {"observed": 1.0, "likely": 0.6, "possible": 0.3, "unknown": 0.0}
    scores: dict[str, float] = {}
    for item in opportunities:
        service = item.get("service")
        if not service or (offered and service not in offered):
            continue
        certainty = str(item.get("certainty", "unknown")).split(".")[-1].lower()
        scores[service] = scores.get(service, 0.0) + weights.get(certainty, 0.2)
    return [s for s, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)][:4]


def _pretty(service: str) -> str:
    raw = service.split(".")[-1]
    try:
        return ServiceOffering(raw).value.replace("_", " ").title()
    except ValueError:
        return raw.replace("_", " ").title()


def compute_completeness(company: Company) -> float:
    """Share of the fields a salesperson actually needs before a call."""
    checks = [
        bool(company.name),
        bool(company.domain),
        bool(company.website_active),
        bool(company.country_code),
        bool(company.city or company.address),
        bool(company.industry_slug),
        bool(company.description),
        bool(company.contacts),
        any(c.contact_type == "email" for c in company.contacts),
        any(c.contact_type == "phone" for c in company.contacts),
        bool(company.decision_makers),
        bool(company.technologies),
        bool(company.signals),
        company.website_record is not None and company.website_record.quality_score is not None,
    ]
    return round(sum(1 for c in checks if c) / len(checks), 3)


def stamp_score(company: Company, outcome: ScoreOutcome) -> None:
    from app.models.company import OpportunityScore

    score = company.score or OpportunityScore(company_id=company.id, category=outcome.category)
    score.total = outcome.total
    score.category = outcome.category
    for key, component in outcome.components.items():
        setattr(score, key, component.points)
    score.breakdown = outcome.breakdown()
    score.recommended_services = outcome.recommended_services
    if company.score is None:
        company.score = score
    company.opportunity_score = outcome.total
    company.opportunity_category = outcome.category
    company.data_completeness = compute_completeness(company)
    company.last_researched_at = datetime.now(UTC)
