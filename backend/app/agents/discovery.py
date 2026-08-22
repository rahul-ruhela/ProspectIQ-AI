"""Global Search and Business Discovery agents.

These two agents turn a campaign brief into real, attributed companies. They never
invent a business: every company row is created from a search result that was actually
returned by a connector, and the result is stored verbatim as evidence.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import func, select

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.connectors.base import SearchResult
from app.connectors.places import PlaceResult, google_places_connector, overpass_connector
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


def _digits(value: str | None) -> str:
    """Phone numbers are formatted a dozen ways; compare only their digits."""
    return re.sub(r"\D", "", value or "")


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
                                    # The place to centre a map lookup on. Unlike
                                    # ``city`` this is always set, so country- and
                                    # region-wide campaigns still reach the map
                                    # directories instead of search only.
                                    "location": location,
                                    "industry_term": term,
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
                        "location": country_names.get(country, country),
                        "industry_term": keyword,
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
    tools = (
        "google_places",
        "openstreetmap",
        "serper",
        "google_cse",
        "searxng",
        "duckduckgo",
    )
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
        if settings.DISCOVERY_FANOUT:
            search_connectors = search_connectors[: max(1, settings.DISCOVERY_MAX_CONNECTORS)]
        else:
            search_connectors = search_connectors[:1]
        places_available = overpass_connector.available or google_places_connector.available
        if not search_connectors and not places_available:
            self.log(
                ctx,
                "No discovery connector is configured. Enable OpenStreetMap or Google Maps "
                "(GOOGLE_MAPS_API_KEY), or configure SERPER_API_KEY, Google CSE, SearXNG or "
                "DuckDuckGo.",
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
            (
                places_created,
                places_matched,
                places_requests,
                places_cost,
                places_slugs,
            ) = await self._discover_places(ctx, queries, max_companies, exclude, created_ids)
            matched_existing += places_matched
            http_requests += places_requests
            connector_cost += places_cost
            if places_created or places_matched:
                connectors_used.extend(places_slugs)
                self.log(
                    ctx,
                    f"Map directories ({', '.join(places_slugs) or 'none'}) contributed "
                    f"{places_created} companies ({places_matched} already known).",
                )

        # --- 2. Free-text search ------------------------------------------
        # Every configured connector is queried, not just the highest-ranked one.
        # Providers index different corners of the web and each has its own daily
        # cap, so fanning out is what turns a thin result set into deep coverage,
        # and one rate-limited provider no longer ends discovery on its own.
        if not search_connectors:
            self.log(ctx, "No search connector configured; using mapped directories only.")
            queries = []
        else:
            self.log(
                ctx,
                "Searching the open web via "
                + ", ".join(c.name for c in search_connectors)
                + ".",
            )

        seen_urls: set[str] = set()
        for spec in queries:
            if len(created_ids) >= max_companies:
                break
            query = spec.get("query", "")
            if not query:
                continue

            results: list[SearchResult] = []
            result_source: dict[str, str] = {}
            for connector in search_connectors:
                try:
                    hits = await connector.search(
                        query, limit=20, country=spec.get("country_code") or None
                    )
                except Exception as exc:
                    self.log(
                        ctx, f"{connector.name} failed for '{query}': {exc}", level="warning"
                    )
                    continue
                http_requests += 1
                connector_cost += connector.cost_per_call_usd
                if hits and connector.slug not in connectors_used:
                    connectors_used.append(connector.slug)
                for hit in hits:
                    if hit.url in seen_urls:
                        continue
                    seen_urls.add(hit.url)
                    result_source[hit.url] = connector.name
                    results.append(hit)

            for result in results:
                if len(created_ids) >= max_companies:
                    break
                source_name = result_source.get(result.url, result.source or "Web search")
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
                    self._add_source(existing, result, source_name, "search_result")
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
                    source=source_name,
                    source_url=result.url,
                    confidence=0.55,  # one source only; verification raises this
                    verification_status=VerificationStatus.NEEDS_VERIFICATION,
                )
                ctx.db.add(company)
                ctx.db.flush()
                self._add_source(company, result, source_name, "search_result")
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
    ) -> tuple[int, int, int, float, list[str]]:
        """Create companies from mapped business records.

        Map directories are the only sources that know about a registered business
        with no website - a Maps or OSM listing carries a name, address, phone and
        category whether or not the owner ever built a site. Those businesses are
        the platform's core prospect, so unlike a web hit they are kept even when
        there is no domain to crawl.

        Returns (created, matched, requests, cost_usd, connector slugs used).
        """
        created_before = len(created_ids)
        matched = 0
        requests = 0
        cost = 0.0
        slugs: list[str] = []

        # One lookup per (location, industry) pair, not per search query.
        seen_areas: set[tuple[str, str, str]] = set()
        for spec in queries:
            if len(created_ids) >= max_companies:
                break
            industry_slug = spec.get("industry_slug") or ""
            country = (spec.get("country_code") or "").upper()
            # ``location`` is set for every plan, including country- and region-wide
            # campaigns; ``city`` is only set when the operator named cities.
            location = spec.get("location") or spec.get("city") or ""
            if not location:
                continue
            industry_term = spec.get("industry_term") or industry_slug.replace("_", " ")
            area = (location.lower(), industry_slug, country)
            if area in seen_areas:
                continue
            seen_areas.add(area)

            places: list[PlaceResult] = []

            # Google Maps first: the deepest index of small local businesses, and
            # the one that reliably lists them without a website.
            if google_places_connector.available:
                try:
                    maps_places = await google_places_connector.search_text(
                        query=f"{industry_term} in {location}",
                        country_code=country or None,
                        limit=max(20, max_companies),
                    )
                except Exception as exc:
                    self.log(ctx, f"Google Maps lookup failed for {location}: {exc}", level="warning")
                    maps_places = []
                else:
                    requests += 1
                    cost += google_places_connector.cost_per_call_usd
                    if google_places_connector.slug not in slugs:
                        slugs.append(google_places_connector.slug)
                places.extend(maps_places)

            if overpass_connector.available and overpass_connector.supports(industry_slug):
                try:
                    osm_places = await overpass_connector.search_area(
                        location=f"{location}, {country}" if country else location,
                        industry_slug=industry_slug,
                        country_code=country or None,
                        limit=max(20, max_companies * 2),
                        name_terms=tuple(industry_term.split()),
                    )
                except Exception as exc:
                    self.log(ctx, f"OpenStreetMap lookup failed for {location}: {exc}", level="warning")
                    osm_places = []
                else:
                    requests += 1
                    if osm_places and overpass_connector.slug not in slugs:
                        slugs.append(overpass_connector.slug)
                places.extend(osm_places)

            for place in places:
                if len(created_ids) >= max_companies:
                    break
                if any(word in place.name.lower() for word in exclude):
                    continue

                domain = domain_of(place.website) if place.website else ""
                if not domain and not settings.DISCOVERY_ALLOW_WEBSITELESS:
                    continue
                if not domain and not (place.phone or place.street):
                    # No site, no phone and no address is not a contactable lead.
                    continue

                existing = self._find_existing_place(ctx, place, domain, location)
                if existing is not None:
                    matched += 1
                    self._merge_place(existing, place, domain)
                    self._add_place_source(existing, place)
                    continue

                company = Company(
                    organization_id=ctx.organization_id,
                    campaign_id=ctx.campaign_id,
                    research_job_id=ctx.research_job_id,
                    name=place.name,
                    domain=domain or None,
                    website=normalise_url(place.website) if place.website else None,
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
                    # A mapped record with a name, address and phone is strong
                    # evidence the business exists even with no site to crawl;
                    # a site on top of that is stronger still.
                    confidence=0.75 if domain else 0.65,
                    verification_status=VerificationStatus.NEEDS_VERIFICATION,
                )
                ctx.db.add(company)
                ctx.db.flush()
                self._add_place_source(company, place)
                created_ids.append(str(company.id))

        return len(created_ids) - created_before, matched, requests, cost, slugs

    @staticmethod
    def _find_existing_place(
        ctx: AgentContext, place: PlaceResult, domain: str, location: str
    ) -> Company | None:
        """Match a mapped record against what is already stored.

        A business with a website deduplicates on domain. One without has no domain
        to key on, so it is matched on phone first (unique in practice) and then on
        name within the same city.
        """
        if domain:
            return ctx.db.execute(
                select(Company).where(
                    Company.organization_id == ctx.organization_id,
                    Company.domain == domain,
                )
            ).scalar_one_or_none()

        phone = _digits(place.phone)
        if phone:
            for candidate in (
                ctx.db.execute(
                    select(Company).where(
                        Company.organization_id == ctx.organization_id,
                        Company.phone.isnot(None),
                    )
                )
                .scalars()
                .all()
            ):
                if _digits(candidate.phone)[-9:] == phone[-9:]:
                    return candidate

        city = (place.city or location or "").strip()
        return ctx.db.execute(
            select(Company)
            .where(
                Company.organization_id == ctx.organization_id,
                func.lower(Company.name) == place.name.strip().lower(),
                func.lower(func.coalesce(Company.city, "")) == city.lower(),
            )
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def _merge_place(company: Company, place: PlaceResult, domain: str) -> None:
        """Fill gaps on an existing record from a stronger mapped source."""
        if domain and not company.domain:
            company.domain = domain
            company.website = normalise_url(place.website)
        for field_name, value in (
            ("phone", place.phone),
            ("address", place.street),
            ("postal_code", place.postal_code),
            ("city", place.city),
            ("category", place.category),
            ("latitude", place.latitude),
            ("longitude", place.longitude),
        ):
            if value and getattr(company, field_name, None) in (None, ""):
                setattr(company, field_name, value)
        company.confidence = min(0.9, company.confidence + 0.1)

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
