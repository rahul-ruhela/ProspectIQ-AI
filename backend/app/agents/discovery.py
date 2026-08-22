"""Global Search and Business Discovery agents.

These two agents turn a campaign brief into real, attributed companies. They never
invent a business: every company row is created from a search result that was actually
returned by a connector, and the result is stored verbatim as evidence.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.connectors.base import SearchResult
from app.connectors.places import PlaceResult, overpass_connector
from app.connectors.search import available_connectors, connector_statuses
from app.core.config import settings
from app.models.company import Company, CompanySource
from app.models.enums import AgentName, VerificationStatus
from app.models.geo import Country, Industry
from app.scraper.crawler import domain_of, normalise_url

# Hosts that list businesses rather than being one. Their results are kept as
# corroborating sources but never become a company on their own.
AGGREGATOR_DOMAINS = {
    "yelp.com", "yellowpages.com", "yell.com", "facebook.com", "linkedin.com",
    "instagram.com", "twitter.com", "x.com", "youtube.com", "indeed.com",
    "glassdoor.com", "tripadvisor.com", "bbb.org", "angi.com", "houzz.com",
    "thumbtack.com", "trustpilot.com", "google.com", "bing.com", "wikipedia.org",
    "crunchbase.com", "zoominfo.com", "manta.com", "cylex.com", "hotfrog.com",
    "reddit.com", "quora.com", "pinterest.com", "amazon.com", "ebay.com",
    "yellowpages.ca", "gelbeseiten.de", "pagesjaunes.fr", "yellowpages.com.au",
    "clutch.co", "goodfirms.co", "expertise.com", "porch.com", "checkatrade.com",
}

# Query templates per country, in the local language where it materially improves recall.
LOCALISED_TEMPLATES: dict[str, tuple[str, ...]] = {
    "DE": ("{industry} {location}", "{industry} Firma {location}", "{industry} Unternehmen {location}"),
    "FR": ("{industry} {location}", "{industry} entreprise {location}", "société {industry} {location}"),
    "AE": ("{industry} {location}", "{industry} company {location} UAE", "{industry} LLC {location}"),
    "ES": ("{industry} {location}", "empresa {industry} {location}"),
    "IT": ("{industry} {location}", "azienda {industry} {location}"),
    "NL": ("{industry} {location}", "{industry} bedrijf {location}"),
}
DEFAULT_TEMPLATES = (
    "{industry} companies in {location}",
    "{industry} services {location}",
    "best {industry} {location}",
    "local {industry} business {location}",
)

TITLE_NOISE = re.compile(
    r"\s*[|\-–—:]\s*(home|homepage|official site|official website|welcome|contact us?|"
    r"about us?|services|home page)\s*$",
    re.IGNORECASE,
)


def clean_company_name(title: str, domain: str) -> str:
    """Derive a usable company name from a search-result title."""
    name = (title or "").strip()
    for _ in range(3):
        cleaned = TITLE_NOISE.sub("", name).strip()
        if cleaned == name:
            break
        name = cleaned
    # Titles are frequently "Brand | Tagline that is long" - keep the branded half.
    if len(name) > 70 and any(sep in name for sep in ("|", " - ", "–")):
        name = re.split(r"\s*[|\-–]\s*", name)[0].strip()
    if not name or len(name) < 2:
        base = domain.split(".")[0].replace("-", " ")
        name = base.title()
    return name[:300]


class GlobalSearchAgent(BaseAgent):
    """Turns campaign targeting into a concrete, localised query plan."""

    key = AgentName.GLOBAL_SEARCH
    display_name = "Global Search Agent"
    role = "International Market Researcher"
    goal = (
        "Translate country, region, city, industry and business-type filters into a "
        "localised search plan that reaches businesses in every supported market."
    )
    tools = ("country_registry", "industry_registry", "query_planner")
    input_schema = {
        "type": "object",
        "properties": {
            "countries": {"type": "array", "items": {"type": "string"}},
            "cities": {"type": "array", "items": {"type": "string"}},
            "industries": {"type": "array", "items": {"type": "string"}},
            "business_types": {"type": "array", "items": {"type": "string"}},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "max_queries": {"type": "integer"},
        },
        "required": ["countries", "industries"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "country_code": {"type": "string"},
                        "city": {"type": "string"},
                        "industry_slug": {"type": "string"},
                    },
                },
            }
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        countries: list[str] = [c.upper() for c in payload.get("countries") or []]
        cities: list[str] = payload.get("cities") or []
        regions: list[str] = payload.get("regions") or []
        industries: list[str] = payload.get("industries") or []
        business_types: list[str] = payload.get("business_types") or []
        keywords: list[str] = payload.get("keywords") or []
        max_queries: int = int(payload.get("max_queries") or 40)

        if not countries:
            return AgentResult.failure("no_countries_selected")

        country_names = {
            row.iso2: row.name
            for row in ctx.db.execute(select(Country).where(Country.iso2.in_(countries)))
            .scalars()
            .all()
        }
        industry_rows = {
            row.slug: row
            for row in ctx.db.execute(select(Industry).where(Industry.slug.in_(industries)))
            .scalars()
            .all()
        }

        # Search terms for a vertical: the seeded keyword list, else the slug itself.
        terms_by_industry: dict[str, list[str]] = {}
        for slug in industries or ["business"]:
            row = industry_rows.get(slug)
            if row is not None and row.search_keywords:
                terms = [t.strip() for t in row.search_keywords.split(",") if t.strip()]
            else:
                terms = [slug.replace("_", " ").replace("-", " ")]
            if business_types:
                terms = [f"{t} {bt}" for t in terms for bt in business_types] or terms
            terms_by_industry[slug] = terms[:4]

        queries: list[dict[str, str]] = []
        for country in countries:
            templates = LOCALISED_TEMPLATES.get(country, DEFAULT_TEMPLATES)
            locations = cities or regions or [country_names.get(country, country)]
            for location in locations:
                for slug, terms in terms_by_industry.items():
                    for term in terms:
                        for template in templates:
                            queries.append(
                                {
                                    "query": template.format(industry=term, location=location),
                                    "country_code": country,
                                    "city": location if cities else "",
                                    "industry_slug": slug,
                                }
                            )
        for keyword in keywords:
            for country in countries:
                queries.append(
                    {
                        "query": f"{keyword} {country_names.get(country, country)}",
                        "country_code": country,
                        "city": "",
                        "industry_slug": industries[0] if industries else "",
                    }
                )

        # De-duplicate while preserving the interleaved country order so every
        # selected market gets coverage even when the query budget is small.
        seen: set[str] = set()
        unique: list[dict[str, str]] = []
        for item in queries:
            if item["query"].lower() in seen:
                continue
            seen.add(item["query"].lower())
            unique.append(item)

        by_country: dict[str, list[dict[str, str]]] = {}
        for item in unique:
            by_country.setdefault(item["country_code"], []).append(item)
        interleaved: list[dict[str, str]] = []
        index = 0
        while len(interleaved) < min(max_queries, len(unique)):
            added = False
            for country in countries:
                bucket = by_country.get(country, [])
                if index < len(bucket) and len(interleaved) < max_queries:
                    interleaved.append(bucket[index])
                    added = True
            if not added:
                break
            index += 1

        self.log(ctx, f"Planned {len(interleaved)} searches across {len(countries)} countries.")
        return AgentResult(ok=True, data={"queries": interleaved}, confidence=0.9)


class BusinessDiscoveryAgent(BaseAgent):
    """Finds real businesses through configured search connectors."""

    key = AgentName.BUSINESS_DISCOVERY
    display_name = "Business Discovery Agent"
    role = "Prospect Sourcer"
    goal = (
        "Find genuine businesses matching the campaign, recording the exact source and "
        "URL for every company so nothing enters the database unattributed."
    )
    tools = ("openstreetmap", "serper", "google_cse", "searxng", "duckduckgo")
    input_schema = {
        "type": "object",
        "properties": {
            "queries": {"type": "array", "items": {"type": "object"}},
            "max_companies": {"type": "integer"},
            "exclude_keywords": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["queries"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "company_ids": {"type": "array", "items": {"type": "string"}},
            "created": {"type": "integer"},
            "matched_existing": {"type": "integer"},
            "connectors_used": {"type": "array", "items": {"type": "string"}},
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        queries: list[dict[str, str]] = payload.get("queries") or []
        max_companies = int(payload.get("max_companies") or settings.MAX_COMPANIES_PER_JOB)
        exclude = [k.lower() for k in payload.get("exclude_keywords") or []]

        search_connectors = available_connectors()
        places_available = overpass_connector.available
        if not search_connectors and not places_available:
            self.log(
                ctx,
                "No discovery connector is configured. Enable OpenStreetMap, or configure "
                "SERPER_API_KEY, Google CSE, SearXNG or DuckDuckGo.",
                level="error",
                connectors=connector_statuses(),
            )
            return AgentResult.failure("no_discovery_connector_available")

        created_ids: list[str] = []
        matched_existing = 0
        http_requests = 0
        connector_cost = 0.0
        connectors_used: list[str] = []
        # Aggregator hits are held back and used to corroborate companies by name.
        pending_corroboration: list[tuple[str, SearchResult]] = []

        # --- 1. Mapped business directories -------------------------------
        # OpenStreetMap gives structured records (name, website, phone, address) that
        # are already tied to a citable element URL, so it runs before free-text search.
        if places_available:
            places_created, places_matched, places_requests = await self._discover_places(
                ctx, queries, max_companies, exclude, created_ids
            )
            matched_existing += places_matched
            http_requests += places_requests
            if places_created:
                connectors_used.append(overpass_connector.slug)
                self.log(
                    ctx,
                    f"OpenStreetMap contributed {places_created} companies "
                    f"({places_matched} already known).",
                )

        # --- 2. Free-text search ------------------------------------------
        if not search_connectors:
            self.log(ctx, "No search connector configured; using mapped directories only.")
            queries = []
        else:
            connector = search_connectors[0]
            connectors_used.append(connector.slug)
            self.log(ctx, f"Searching the open web via {connector.name}.")

        for spec in queries:
            if len(created_ids) >= max_companies:
                break
            query = spec.get("query", "")
            if not query:
                continue
            try:
                results = await connector.search(
                    query, limit=20, country=spec.get("country_code") or None
                )
            except Exception as exc:
                self.log(ctx, f"Search failed for '{query}': {exc}", level="warning")
                continue
            http_requests += 1
            connector_cost += connector.cost_per_call_usd

            for result in results:
                if len(created_ids) >= max_companies:
                    break
                domain = domain_of(result.url)
                if not domain or "." not in domain:
                    continue
                haystack = f"{result.title} {result.snippet}".lower()
                if any(word in haystack for word in exclude):
                    continue
                if self._is_aggregator(domain):
                    pending_corroboration.append((result.title.lower(), result))
                    continue

                existing = ctx.db.execute(
                    select(Company).where(
                        Company.organization_id == ctx.organization_id,
                        Company.domain == domain,
                    )
                ).scalar_one_or_none()

                if existing is not None:
                    matched_existing += 1
                    self._add_source(existing, result, connector.name, "search_result")
                    continue

                company = Company(
                    organization_id=ctx.organization_id,
                    campaign_id=ctx.campaign_id,
                    research_job_id=ctx.research_job_id,
                    name=clean_company_name(result.title, domain),
                    domain=domain,
                    website=normalise_url(result.url),
                    industry_slug=spec.get("industry_slug") or None,
                    country_code=(spec.get("country_code") or "").upper()[:2] or None,
                    city=spec.get("city") or None,
                    description=result.snippet[:2000] or None,
                    source=connector.name,
                    source_url=result.url,
                    confidence=0.55,  # one source only; verification raises this
                    verification_status=VerificationStatus.NEEDS_VERIFICATION,
                )
                ctx.db.add(company)
                ctx.db.flush()
                self._add_source(company, result, connector.name, "search_result")
                created_ids.append(str(company.id))

        # Corroborate: a directory listing that names a discovered company is a second source.
        if pending_corroboration and created_ids:
            companies = (
                ctx.db.execute(
                    select(Company).where(Company.id.in_([uuid.UUID(c) for c in created_ids]))
                )
                .scalars()
                .all()
            )
            for company in companies:
                needle = company.name.lower()[:24]
                for title, result in pending_corroboration:
                    if needle and needle in title:
                        self._add_source(company, result, "Directory listing", "directory_listing")
                        company.confidence = min(0.85, company.confidence + 0.15)
                        break

        ctx.connector_cost_usd += connector_cost
        self.log(
            ctx,
            f"Discovered {len(created_ids)} new companies "
            f"({matched_existing} already known) from {http_requests} requests via "
            f"{', '.join(connectors_used) or 'no connector'}.",
        )
        return AgentResult(
            ok=True,
            data={
                "company_ids": created_ids,
                "created": len(created_ids),
                "matched_existing": matched_existing,
                "connectors_used": connectors_used,
            },
            confidence=0.8 if created_ids else 0.3,
            http_requests=http_requests,
            cost_usd=connector_cost,
        )

    async def _discover_places(
        self,
        ctx: AgentContext,
        queries: list[dict[str, str]],
        max_companies: int,
        exclude: list[str],
        created_ids: list[str],
    ) -> tuple[int, int, int]:
        """Create companies from mapped business records. Returns (created, matched, requests)."""
        created_before = len(created_ids)
        matched = 0
        requests = 0

        # One Overpass call per (location, industry) pair, not per search query.
        seen_areas: set[tuple[str, str, str]] = set()
        for spec in queries:
            industry_slug = spec.get("industry_slug") or ""
            country = (spec.get("country_code") or "").upper()
            location = spec.get("city") or ""
            if not location:
                # Country-wide targeting: Overpass needs a place to centre on, and the
                # campaign did not name one, so leave this to the search connectors.
                continue
            if not overpass_connector.supports(industry_slug):
                continue
            area = (location.lower(), industry_slug, country)
            if area in seen_areas:
                continue
            seen_areas.add(area)
            if len(created_ids) >= max_companies:
                break

            try:
                places = await overpass_connector.search_area(
                    location=f"{location}, {country}" if country else location,
                    industry_slug=industry_slug,
                    country_code=country or None,
                    limit=max(20, max_companies * 2),
                )
            except Exception as exc:
                self.log(ctx, f"OpenStreetMap lookup failed for {location}: {exc}", level="warning")
                continue
            requests += 1

            for place in places:
                if len(created_ids) >= max_companies:
                    break
                if any(word in place.name.lower() for word in exclude):
                    continue
                domain = domain_of(place.website) if place.website else ""
                if not place.website or not domain:
                    # Without a website there is nothing to research and no way to
                    # deduplicate reliably, so it is not turned into a prospect.
                    continue

                existing = ctx.db.execute(
                    select(Company).where(
                        Company.organization_id == ctx.organization_id,
                        Company.domain == domain,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    matched += 1
                    self._add_place_source(existing, place)
                    continue

                company = Company(
                    organization_id=ctx.organization_id,
                    campaign_id=ctx.campaign_id,
                    research_job_id=ctx.research_job_id,
                    name=place.name,
                    domain=domain,
                    website=normalise_url(place.website),
                    industry_slug=industry_slug or None,
                    category=place.category or None,
                    country_code=(place.country_code or country)[:2] or None,
                    city=place.city or location,
                    address=place.street or None,
                    postal_code=place.postal_code or None,
                    latitude=place.latitude,
                    longitude=place.longitude,
                    phone=place.phone or None,
                    source=place.source,
                    source_url=place.source_url,
                    # A mapped record with a name, website and address is stronger
                    # evidence than a single search hit.
                    confidence=0.75,
                    verification_status=VerificationStatus.NEEDS_VERIFICATION,
                )
                ctx.db.add(company)
                ctx.db.flush()
                self._add_place_source(company, place)
                created_ids.append(str(company.id))

        return len(created_ids) - created_before, matched, requests

    @staticmethod
    def _add_place_source(company: Company, place: PlaceResult) -> None:
        for existing in company.sources:
            if existing.source_url == place.source_url:
                return
        company.sources.append(
            CompanySource(
                source_type="directory_listing",
                title=place.name[:500],
                snippet=", ".join(
                    part for part in (place.street, place.city, place.phone) if part
                )[:2000],
                source=place.source,
                source_url=place.source_url,
                confidence=0.85,
                verification_status=VerificationStatus.VERIFIED,
                raw=place.raw or None,
            )
        )

    @staticmethod
    def _is_aggregator(domain: str) -> bool:
        return any(domain == d or domain.endswith("." + d) for d in AGGREGATOR_DOMAINS)

    @staticmethod
    def _add_source(company: Company, result: SearchResult, source: str, source_type: str) -> None:
        for existing in company.sources:
            if existing.source_url == result.url:
                return
        company.sources.append(
            CompanySource(
                source_type=source_type,
                title=result.title[:500],
                snippet=result.snippet[:2000],
                source=source,
                source_url=result.url,
                confidence=0.7,
                verification_status=VerificationStatus.VERIFIED,
                raw=result.raw or None,
            )
        )
