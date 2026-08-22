"""Website Scraping, Website Intelligence and Technology Detection agents."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.utils import load_company
from app.models.company import Company, Technology, Website, WebsiteFeature, WebsitePage
from app.models.enums import AgentName, Certainty, VerificationStatus
from app.scraper.crawler import CrawlResult, crawl_site
from app.scraper.extract import ParsedPage
from app.scraper.signatures import (
    FEATURE_SIGNALS,
    OPPORTUNITY_FEATURES,
    detect_technologies,
)

# Crawl results live in memory for the duration of one company's research pass so the
# scraping agent runs once and the analysis agents reuse its output.
_CRAWL_CACHE: dict[str, CrawlResult] = {}


def cache_crawl(company_id: str, result: CrawlResult) -> None:
    _CRAWL_CACHE[company_id] = result


def get_cached_crawl(company_id: str) -> CrawlResult | None:
    return _CRAWL_CACHE.get(company_id)


def clear_crawl_cache(company_id: str) -> None:
    _CRAWL_CACHE.pop(company_id, None)


class WebsiteScrapingAgent(BaseAgent):
    """Crawls the company website and persists the pages it actually fetched."""

    key = AgentName.WEBSITE_SCRAPING
    display_name = "Website Scraping Agent"
    role = "Web Data Collector"
    goal = (
        "Fetch the homepage, about, services, pricing, contact, team, booking, careers, "
        "blog and FAQ pages of a company website, honouring robots.txt and rate limits."
    )
    tools = ("httpx", "beautifulsoup", "playwright", "robots_txt")
    input_schema = {
        "type": "object",
        "properties": {"company_id": {"type": "string"}, "max_pages": {"type": "integer"}},
        "required": ["company_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "reachable": {"type": "boolean"},
            "pages_crawled": {"type": "integer"},
            "page_types": {"type": "array", "items": {"type": "string"}},
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        company = load_company(ctx, payload)
        if company is None:
            return AgentResult.failure("company_not_found")
        if not company.website:
            self.log(ctx, f"{company.name} has no website on record; nothing to crawl.")
            company.website_active = False
            return AgentResult(ok=True, data={"reachable": False, "pages_crawled": 0}, confidence=0.4)

        crawl = await crawl_site(company.website, max_pages=payload.get("max_pages"))
        cache_crawl(str(company.id), crawl)

        website = company.website_record or Website(url=company.website)
        website.url = company.website
        website.final_url = crawl.final_url or None
        website.http_status = crawl.http_status
        website.is_reachable = crawl.reachable
        website.is_https = crawl.is_https
        website.load_time_ms = crawl.load_time_ms
        website.pages_crawled = len(crawl.pages)
        website.crawled_at = datetime.now(UTC)
        website.source = "Website crawl"
        website.source_url = crawl.final_url or company.website
        website.confidence = 0.95 if crawl.reachable else 0.6
        website.verification_status = (
            VerificationStatus.VERIFIED if crawl.reachable else VerificationStatus.NEEDS_VERIFICATION
        )
        website.last_verified_at = datetime.now(UTC)

        if crawl.pages:
            home = crawl.pages[0]
            website.title = home.title[:500] or None
            website.meta_description = home.meta_description or None
            website.language = home.language or None
            website.is_mobile_friendly = home.has_viewport_meta
            website.copyright_year = home.copyright_year
            website.total_bytes = sum(len(p.raw_html) for p in crawl.pages)

        if company.website_record is None:
            company.website_record = website
        ctx.db.flush()

        # Replace the page set so a re-run reflects the site as it is today.
        for existing in list(website.pages):
            ctx.db.delete(existing)
        for page in crawl.pages:
            website.pages.append(
                WebsitePage(
                    url=page.url[:2048],
                    page_type=page.page_type,
                    http_status=200,
                    title=page.title[:500] or None,
                    word_count=page.word_count,
                    text_excerpt=page.text[:4000] or None,
                    headings=page.headings[:20],
                    forms_count=page.forms_count,
                    fetched_at=datetime.now(UTC),
                )
            )

        company.website_active = crawl.reachable
        if crawl.pages and crawl.pages[0].social_links:
            company.linkedin_url = crawl.pages[0].social_links.get("linkedin.com") or company.linkedin_url
            company.facebook_url = crawl.pages[0].social_links.get("facebook.com") or company.facebook_url

        self.log(
            ctx,
            f"Crawled {len(crawl.pages)} pages of {company.website} "
            f"({'reachable' if crawl.reachable else 'unreachable: ' + str(crawl.error)}).",
        )
        self.send(ctx, AgentName.WEBSITE_INTELLIGENCE, "site_crawled", {"company_id": str(company.id)})

        return AgentResult(
            ok=True,
            data={
                "reachable": crawl.reachable,
                "pages_crawled": len(crawl.pages),
                "page_types": sorted(crawl.page_types()),
                "error": crawl.error,
            },
            confidence=0.95 if crawl.reachable else 0.5,
            http_requests=crawl.requests_made,
        )


class TechnologyDetectionAgent(BaseAgent):
    """Fingerprints the technology stack from the HTML and response headers."""

    key = AgentName.TECHNOLOGY_DETECTION
    display_name = "Technology Detection Agent"
    role = "Technical Analyst"
    goal = (
        "Identify the CMS, frontend framework, CRM, booking, payment, analytics and "
        "support tooling a company runs, storing the exact signature that proved it."
    )
    tools = ("signature_matcher", "header_analysis")
    input_schema = {
        "type": "object",
        "properties": {"company_id": {"type": "string"}},
        "required": ["company_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "technologies": {"type": "array", "items": {"type": "string"}},
            "categories": {"type": "array", "items": {"type": "string"}},
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        company = load_company(ctx, payload)
        if company is None:
            return AgentResult.failure("company_not_found")
        crawl = get_cached_crawl(str(company.id))
        if crawl is None or not crawl.pages:
            return AgentResult(
                ok=True,
                data={"technologies": [], "reason": "no_crawl_data"},
                confidence=0.0,
            )

        # Scan every fetched page: analytics and chat widgets often only load on inner pages.
        found: dict[str, Any] = {}
        for page in crawl.pages:
            for match in detect_technologies(page.raw_html, crawl.headers, page.url):
                if match.slug not in found:
                    found[match.slug] = match

        existing = {tech.slug for tech in company.technologies}
        for slug, match in found.items():
            if slug in existing:
                continue
            company.technologies.append(
                Technology(
                    slug=match.slug,
                    name=match.name,
                    category=match.category,
                    version=match.version,
                    matched_signature=match.matched_signature,
                    source="Website fingerprint",
                    source_url=match.source_url,
                    confidence=match.confidence,
                    verification_status=VerificationStatus.VERIFIED,
                    last_verified_at=datetime.now(UTC),
                )
            )

        self.log(
            ctx,
            f"Detected {len(found)} technologies on {company.domain}: "
            f"{', '.join(sorted(m.name for m in found.values())) or 'none'}.",
        )
        return AgentResult(
            ok=True,
            data={
                "technologies": sorted(m.name for m in found.values()),
                "categories": sorted({m.category for m in found.values()}),
            },
            confidence=0.9 if found else 0.5,
        )


class WebsiteIntelligenceAgent(BaseAgent):
    """Judges the website as a sales asset and records what is missing, with evidence."""

    key = AgentName.WEBSITE_INTELLIGENCE
    display_name = "Website Intelligence Agent"
    role = "Conversion Analyst"
    goal = (
        "Assess website quality, mobile experience, trust signals, lead capture and the "
        "customer journey, and record each present or absent capability with evidence."
    )
    tools = ("feature_detector", "quality_scorer")
    input_schema = {
        "type": "object",
        "properties": {"company_id": {"type": "string"}},
        "required": ["company_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "quality_score": {"type": "number"},
            "present_features": {"type": "array", "items": {"type": "string"}},
            "missing_features": {"type": "array", "items": {"type": "string"}},
            "weaknesses": {"type": "array", "items": {"type": "string"}},
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        company = load_company(ctx, payload)
        if company is None:
            return AgentResult.failure("company_not_found")
        website = company.website_record
        crawl = get_cached_crawl(str(company.id))
        if website is None or crawl is None or not crawl.pages:
            return AgentResult(ok=True, data={"reason": "no_crawl_data"}, confidence=0.0)

        tech_slugs = {tech.slug for tech in company.technologies}
        present: dict[str, tuple[str, str]] = {}  # feature -> (evidence url, matched text)

        for feature, needles in FEATURE_SIGNALS.items():
            for page in crawl.pages:
                haystack = f"{page.text.lower()} {page.raw_html.lower()}"
                if feature == "contact_form":
                    if page.forms_count > 0:
                        present[feature] = (page.url, f"{page.forms_count} form(s) on page")
                        break
                    continue
                if feature == "multilingual":
                    if "hreflang" in page.raw_html.lower():
                        present[feature] = (page.url, "hreflang alternates declared")
                        break
                    continue
                matched = next((n for n in needles if n in haystack), None)
                if matched:
                    present[feature] = (page.url, matched)
                    break

        # Technology detections are stronger evidence than text matches.
        if tech_slugs & {"intercom", "drift", "tawkto", "zendesk", "livechat", "crisp"}:
            present.setdefault("live_chat", (website.final_url or website.url, "chat widget script"))
        if tech_slugs & {"calendly", "acuity", "housecallpro", "jobber", "servicetitan"}:
            present.setdefault("online_booking", (website.final_url or website.url, "booking widget script"))
        if tech_slugs & {"shopify", "stripe", "square", "paypal"}:
            present.setdefault("ecommerce", (website.final_url or website.url, "payment/commerce script"))

        page_types = crawl.page_types()
        if "booking" in page_types:
            present.setdefault("online_booking", (crawl.page_by_type("booking").url, "booking page"))
        if "blog" in page_types:
            present.setdefault("blog", (crawl.page_by_type("blog").url, "blog section"))
        if "faq" in page_types:
            present.setdefault("faq", (crawl.page_by_type("faq").url, "FAQ page"))
        if "pricing" in page_types:
            present.setdefault("pricing_published", (crawl.page_by_type("pricing").url, "pricing page"))
        if "portal" in page_types:
            present.setdefault("customer_portal", (crawl.page_by_type("portal").url, "portal/login page"))

        # Persist every capability as present or absent - absence is the sellable finding.
        for existing in list(website.features):
            ctx.db.delete(existing)
        ctx.db.flush()

        missing: list[str] = []
        for feature in FEATURE_SIGNALS:
            if feature in present:
                url, matched = present[feature]
                website.features.append(
                    WebsiteFeature(
                        feature_key=feature,
                        present=True,
                        certainty=Certainty.OBSERVED,
                        detail=f"Matched: {matched}"[:1000],
                        source="Website crawl",
                        source_url=url,
                        confidence=0.9,
                        verification_status=VerificationStatus.VERIFIED,
                        last_verified_at=datetime.now(UTC),
                    )
                )
            else:
                # We only claim absence for pages we actually fetched.
                certainty = Certainty.OBSERVED if len(crawl.pages) >= 4 else Certainty.LIKELY
                website.features.append(
                    WebsiteFeature(
                        feature_key=feature,
                        present=False,
                        certainty=certainty,
                        detail=OPPORTUNITY_FEATURES.get(
                            feature, f"No evidence of {feature.replace('_', ' ')} in crawled pages."
                        )[:1000],
                        source="Website crawl",
                        source_url=website.final_url or website.url,
                        confidence=0.75 if certainty == Certainty.OBSERVED else 0.55,
                        verification_status=VerificationStatus.VERIFIED,
                        last_verified_at=datetime.now(UTC),
                    )
                )
                if feature in OPPORTUNITY_FEATURES:
                    missing.append(feature)

        quality, weaknesses = self._score_quality(crawl, website, present, tech_slugs)
        website.quality_score = quality

        self.log(
            ctx,
            f"Website quality {quality:.0f}/100 for {company.domain}. "
            f"Missing: {', '.join(missing) or 'nothing material'}.",
        )
        return AgentResult(
            ok=True,
            data={
                "quality_score": quality,
                "present_features": sorted(present),
                "missing_features": missing,
                "weaknesses": weaknesses,
            },
            confidence=0.85,
        )

    @staticmethod
    def _score_quality(
        crawl: CrawlResult,
        website: Website,
        present: dict[str, tuple[str, str]],
        tech_slugs: set[str],
    ) -> tuple[float, list[str]]:
        """A transparent 0-100 website quality score. Lower means more opportunity."""
        score = 100.0
        weaknesses: list[str] = []

        def penalise(points: float, reason: str) -> None:
            nonlocal score
            score -= points
            weaknesses.append(reason)

        if not website.is_https:
            penalise(12, "Site is not served over HTTPS.")
        if not website.is_mobile_friendly:
            penalise(15, "No mobile viewport meta tag - likely poor mobile experience.")
        if website.load_time_ms and website.load_time_ms > 3000:
            penalise(10, f"Homepage responded in {website.load_time_ms} ms.")
        current_year = datetime.now(UTC).year
        if website.copyright_year and website.copyright_year < current_year - 2:
            penalise(12, f"Copyright notice still reads {website.copyright_year}.")
        if "contact_form" not in present:
            penalise(12, "No contact form found on any crawled page.")
        if "online_booking" not in present:
            penalise(8, "No online booking or scheduling.")
        if "live_chat" not in present:
            penalise(6, "No live chat or chatbot.")
        if "testimonials" not in present and "trust_badges" not in present:
            penalise(8, "No visible trust signals (reviews, certifications).")
        if "case_studies" not in present:
            penalise(4, "No case studies or proof of work.")
        if len(crawl.pages) <= 2:
            penalise(10, "Very small site - little content for search or trust.")
        home = crawl.pages[0]
        if home.word_count < 250:
            penalise(8, "Thin homepage content.")
        if not home.meta_description:
            penalise(4, "Missing meta description.")
        if tech_slugs & {"godaddy_builder", "wix", "squarespace"} and "ecommerce" not in present:
            weaknesses.append("Built on a template site builder - limited automation options.")

        return max(0.0, min(100.0, round(score, 1))), weaknesses
