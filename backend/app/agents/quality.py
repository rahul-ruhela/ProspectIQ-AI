"""Company Verification, Lead Quality and Opportunity Scoring agents."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.utils import load_company
from app.models.company import Company, CompanyVerification
from app.models.enums import AgentName, VerificationStatus
from app.services.scoring import compute_completeness, score_company, stamp_score

# Wording that indicates a parked domain, a template placeholder or an expired site.
SPAM_MARKERS = (
    "this domain is for sale", "buy this domain", "domain parking", "coming soon",
    "under construction", "lorem ipsum", "your website title", "sample page",
    "default web site page", "site not published", "account suspended",
)


class CompanyVerificationAgent(BaseAgent):
    """Confirms a company is real, active, relevant and not a duplicate."""

    key = AgentName.COMPANY_VERIFICATION
    display_name = "Company Verification Agent"
    role = "Data Integrity Officer"
    goal = (
        "Confirm the company exists, its website is live, it matches the target industry, "
        "it is not a duplicate and it is not a parked or spam domain."
    )
    tools = ("source_corroboration", "duplicate_check", "spam_detection")
    input_schema = {
        "type": "object",
        "properties": {
            "company_id": {"type": "string"},
            "target_industries": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["company_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "exists_confirmed": {"type": "boolean"},
            "duplicate_found": {"type": "boolean"},
            "spam_suspected": {"type": "boolean"},
            "confidence": {"type": "number"},
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        company = load_company(ctx, payload)
        if company is None:
            return AgentResult.failure("company_not_found")

        website = company.website_record
        source_count = len({s.source_url for s in company.sources})
        website_active = bool(website and website.is_reachable)

        # Duplicate: the same domain, or a very close name in the same city.
        duplicate = ctx.db.execute(
            select(Company).where(
                Company.organization_id == company.organization_id,
                Company.id != company.id,
                Company.domain == company.domain,
            )
        ).scalar_one_or_none()
        if duplicate is None and company.city:
            duplicate = ctx.db.execute(
                select(Company).where(
                    Company.organization_id == company.organization_id,
                    Company.id != company.id,
                    Company.name == company.name,
                    Company.city == company.city,
                )
            ).scalar_one_or_none()

        spam = False
        spam_reason = ""
        thin_content = False
        if website is not None and website.pages:
            corpus = " ".join((p.text_excerpt or "").lower() for p in website.pages[:3])
            marker = next((m for m in SPAM_MARKERS if m in corpus), None)
            if marker:
                spam, spam_reason = True, f"Page text contains '{marker}'."
            elif sum(p.word_count for p in website.pages) < 60:
                # A near-empty body is usually a client-rendered app, not a parked
                # domain. That is a rendering limitation on our side, so the company
                # is held for verification rather than accused of being fake.
                thin_content = True

        target_industries = set(payload.get("target_industries") or [])
        industry_match: bool | None = None
        if target_industries:
            industry_match = company.industry_slug in target_industries if company.industry_slug else None

        # A mapped listing (Google Maps / OpenStreetMap) that carries a street
        # address or a phone number is direct evidence the business is registered
        # and trading. Requiring a live website on top of that would discard every
        # small business that never built one - exactly the segment being targeted.
        directory_confirmed = bool(
            any(src.source_type == "directory_listing" for src in company.sources)
            and (company.address or company.phone)
        )
        exists_confirmed = website_active or directory_confirmed or source_count >= 2
        confidence = 0.3
        if website_active:
            confidence += 0.4
        elif directory_confirmed:
            confidence += 0.3
        if source_count >= 2:
            confidence += 0.2
        if source_count >= 3:
            confidence += 0.1
        if spam:
            confidence = min(confidence, 0.2)
        confidence = round(min(1.0, confidence), 3)

        status = VerificationStatus.VERIFIED
        if spam or duplicate is not None:
            status = VerificationStatus.REJECTED
        elif not exists_confirmed or thin_content:
            status = VerificationStatus.NEEDS_VERIFICATION

        notes: list[str] = [f"{source_count} independent source(s)."]
        if website_active:
            notes.append("Website responded successfully.")
        elif directory_confirmed:
            notes.append(
                "No website; confirmed by a mapped directory listing with a verified "
                "address or phone number."
            )
        elif website is not None:
            notes.append(f"Website unreachable (HTTP {website.http_status}).")
        if duplicate is not None:
            notes.append(f"Duplicate of existing company {duplicate.id}.")
        if spam:
            notes.append(spam_reason)
        if thin_content:
            notes.append(
                "Almost no text was extracted. The site is probably JavaScript-rendered; "
                "enable ENABLE_PLAYWRIGHT to read it."
            )
        if industry_match is False:
            notes.append(
                f"Industry '{company.industry_slug}' is outside the campaign targets."
            )

        ctx.db.add(
            CompanyVerification(
                company_id=company.id,
                exists_confirmed=exists_confirmed,
                website_active=website_active,
                industry_match=industry_match,
                duplicate_found=duplicate is not None,
                spam_suspected=spam,
                independent_source_count=source_count,
                status=status,
                confidence=confidence,
                notes=" ".join(notes),
                checked_at=datetime.now(UTC),
            )
        )

        company.verification_status = status
        company.confidence = confidence
        company.last_verified_at = datetime.now(UTC)
        if duplicate is not None:
            company.is_duplicate_of = duplicate.id
            company.is_rejected = True
            company.rejection_reason = "Duplicate of an existing company record."
        elif spam:
            company.is_rejected = True
            company.rejection_reason = spam_reason or "Parked or placeholder website."

        self.log(ctx, f"Verification of {company.name}: {status}. {' '.join(notes)}")
        return AgentResult(
            ok=True,
            data={
                "status": str(status),
                "exists_confirmed": exists_confirmed,
                "duplicate_found": duplicate is not None,
                "spam_suspected": spam,
                "thin_content": thin_content,
                "industry_match": industry_match,
                "confidence": confidence,
                "notes": notes,
            },
            confidence=confidence,
        )


class LeadQualityAgent(BaseAgent):
    """Rejects anything that would waste a salesperson's time and scores what remains."""

    key = AgentName.LEAD_QUALITY
    display_name = "Lead Quality Agent"
    role = "Quality Gatekeeper"
    goal = (
        "Reject fake companies, dead websites, wrong industries, duplicates and low "
        "confidence records, and give every survivor a lead quality score."
    )
    tools = ("rule_engine", "completeness_check")
    input_schema = {
        "type": "object",
        "properties": {
            "company_id": {"type": "string"},
            "target_industries": {"type": "array", "items": {"type": "string"}},
            "require_website": {"type": "boolean"},
            "min_confidence": {"type": "number"},
        },
        "required": ["company_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "accepted": {"type": "boolean"},
            "lead_quality_score": {"type": "number"},
            "rejection_reason": {"type": "string"},
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        company = load_company(ctx, payload)
        if company is None:
            return AgentResult.failure("company_not_found")

        require_website = bool(payload.get("require_website", True))
        min_confidence = float(payload.get("min_confidence") or 0.35)
        target_industries = set(payload.get("target_industries") or [])

        reasons: list[str] = []
        if company.is_duplicate_of:
            reasons.append("Duplicate record.")
        if company.verification_status == VerificationStatus.REJECTED and company.rejection_reason:
            reasons.append(company.rejection_reason)
        if require_website and company.website_active is not True:
            reasons.append("Website is not reachable.")
        if company.confidence < min_confidence:
            reasons.append(f"Source confidence {company.confidence:.2f} is below {min_confidence:.2f}.")
        if target_industries and company.industry_slug and company.industry_slug not in target_industries:
            reasons.append(f"Industry '{company.industry_slug}' is outside campaign targets.")
        if not company.contacts and not company.website_active and not company.phone:
            reasons.append("No contact route of any kind.")

        completeness = compute_completeness(company)
        # Quality blends how much we know with how well verified it is. The last
        # term measures whether the business can actually be reached: a live site
        # is the strongest signal, a listed phone number is a weaker but real one,
        # so a website-less business is discounted rather than zeroed.
        reachability = 1.0 if company.website_active else (0.6 if company.phone else 0.0)
        quality = round(
            100 * (0.5 * completeness + 0.3 * company.confidence + 0.2 * reachability),
            1,
        )

        accepted = not reasons
        company.lead_quality_score = quality
        company.data_completeness = completeness
        if not accepted:
            company.is_rejected = True
            company.rejection_reason = " ".join(reasons)[:400]
        else:
            company.is_rejected = False
            company.rejection_reason = None

        self.log(
            ctx,
            f"{'Accepted' if accepted else 'Rejected'} {company.name} "
            f"(quality {quality}). {' '.join(reasons)}",
            level="info" if accepted else "warning",
        )
        return AgentResult(
            ok=True,
            data={
                "accepted": accepted,
                "lead_quality_score": quality,
                "completeness": completeness,
                "rejection_reason": " ".join(reasons) or None,
            },
            confidence=0.9,
        )


class OpportunityScoringAgent(BaseAgent):
    """Produces the explainable 0-100 opportunity score and its breakdown."""

    key = AgentName.OPPORTUNITY_SCORING
    display_name = "Opportunity Scoring Agent"
    role = "Prioritisation Analyst"
    goal = (
        "Score every prospect 0-100 across nine weighted components and record the "
        "reasoning behind each component so a human can audit the ranking."
    )
    tools = ("scoring_engine", "weight_registry")
    input_schema = {
        "type": "object",
        "properties": {
            "company_id": {"type": "string"},
            "offered_services": {"type": "array", "items": {"type": "string"}},
            "opportunities": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["company_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "total": {"type": "number"},
            "category": {"type": "string"},
            "breakdown": {"type": "object"},
            "recommended_services": {"type": "array", "items": {"type": "string"}},
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        company = load_company(ctx, payload)
        if company is None:
            return AgentResult.failure("company_not_found")

        outcome = score_company(
            ctx.db,
            company,
            offered_services=payload.get("offered_services"),
            opportunities=payload.get("opportunities"),
        )
        stamp_score(company, outcome)

        self.log(
            ctx,
            f"Scored {company.name}: {outcome.total}/100 ({outcome.category}). "
            f"Top services: {', '.join(outcome.recommended_services) or 'none'}.",
        )
        return AgentResult(
            ok=True,
            data={
                "total": outcome.total,
                "category": str(outcome.category),
                "breakdown": outcome.breakdown(),
                "recommended_services": outcome.recommended_services,
            },
            confidence=0.95,
        )
