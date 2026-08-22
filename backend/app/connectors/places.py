"""OpenStreetMap business discovery via Nominatim + Overpass.

This is the platform's keyless, terms-friendly discovery source. Overpass returns
structured business records — name, website, phone, address, opening hours — that are
already attributed to a specific OSM element, so every company created from it has a
citable source URL from the moment it enters the database.

Both APIs are volunteer-run. The connector geocodes at most once per location, caches
results for the process lifetime, paces requests, and fails over between Overpass
mirrors rather than hammering a single instance.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.connectors.base import ConnectorStatus
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
)

# Industry slug -> the OSM tag filters that identify that kind of business.
# Only tags that genuinely describe the vertical are listed; a slug with no mapping
# falls back to search connectors rather than returning loosely related places.
OSM_TAGS: dict[str, tuple[str, ...]] = {
    "hvac": ('["craft"="hvac"]', '["shop"="hvac"]', '["craft"="heating_engineer"]'),
    "plumbing": ('["craft"="plumber"]',),
    "electrical": ('["craft"="electrician"]',),
    "roofing": ('["craft"="roofer"]',),
    "landscaping": ('["craft"="gardener"]', '["shop"="garden_centre"]'),
    "construction": ('["craft"="builder"]', '["office"="construction_company"]'),
    "pest_control": ('["craft"="pest_control"]',),
    "cleaning": ('["shop"="dry_cleaning"]', '["craft"="cleaning"]', '["office"="cleaning"]'),
    "dental": ('["amenity"="dentist"]', '["healthcare"="dentist"]'),
    "medical": ('["amenity"="doctors"]', '["amenity"="clinic"]', '["healthcare"="doctor"]'),
    "veterinary": ('["amenity"="veterinary"]',),
    "physiotherapy": ('["healthcare"="physiotherapist"]', '["shop"="chiropractor"]'),
    "legal": ('["office"="lawyer"]',),
    "accounting": ('["office"="accountant"]', '["office"="tax_advisor"]'),
    "real_estate": ('["office"="estate_agent"]',),
    "property_management": ('["office"="property_management"]',),
    "insurance": ('["office"="insurance"]',),
    "automotive": ('["shop"="car_repair"]', '["shop"="car"]', '["shop"="tyres"]'),
    "fitness": ('["leisure"="fitness_centre"]', '["shop"="sports"]'),
    "beauty": ('["shop"="hairdresser"]', '["shop"="beauty"]', '["leisure"="spa"]'),
    "restaurant": ('["amenity"="restaurant"]', '["amenity"="cafe"]'),
    "hospitality": ('["tourism"="hotel"]', '["tourism"="guest_house"]'),
    "education": ('["amenity"="driving_school"]', '["amenity"="language_school"]', '["office"="educational_institution"]'),
    "logistics": ('["office"="logistics"]', '["shop"="courier"]'),
    "manufacturing": ('["man_made"="works"]', '["office"="company"]["industrial"]'),
    "wholesale": ('["shop"="wholesale"]', '["shop"="trade"]'),
    "marketing_agency": ('["office"="advertising_agency"]', '["office"="marketing"]'),
    "recruitment": ('["office"="employment_agency"]',),
    "financial_services": ('["office"="financial"]', '["office"="financial_advisor"]'),
    "security": ('["office"="security"]', '["craft"="locksmith"]'),
    "moving": ('["shop"="moving_company"]', '["office"="moving_company"]'),
    "solar": ('["craft"="solar"]', '["shop"="solar"]'),
    "it_services": ('["office"="it"]', '["office"="telecommunication"]', '["shop"="computer"]'),
}

# City-scale radius in metres. Large enough to cover a metro, small enough to stay local.
DEFAULT_RADIUS_M = 25_000


@dataclass(slots=True)
class PlaceResult:
    """A structured business record from a mapping/directory source."""

    name: str
    website: str = ""
    phone: str = ""
    street: str = ""
    city: str = ""
    postal_code: str = ""
    country_code: str = ""
    latitude: float | None = None
    longitude: float | None = None
    category: str = ""
    source: str = "OpenStreetMap"
    source_url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class OverpassConnector:
    """Keyless business discovery from OpenStreetMap."""

    slug = "openstreetmap"
    name = "OpenStreetMap (Overpass)"
    kind = "directory"
    requires_api_key = False
    cost_per_call_usd = 0.0

    def __init__(self) -> None:
        self._geocode_cache: dict[str, tuple[float, float] | None] = {}
        self._last_nominatim_at = 0.0

    @property
    def available(self) -> bool:
        return settings.ENABLE_OPENSTREETMAP

    @property
    def unavailable_reason(self) -> str:
        return "ENABLE_OPENSTREETMAP is false."

    def status(self) -> ConnectorStatus:
        return ConnectorStatus(
            slug=self.slug,
            name=self.name,
            available=self.available,
            reason="Ready. Keyless; covers mapped businesses worldwide."
            if self.available
            else self.unavailable_reason,
        )

    def supports(self, industry_slug: str | None) -> bool:
        return bool(industry_slug) and industry_slug in OSM_TAGS

    def _client(self) -> httpx.AsyncClient:
        # Nominatim's usage policy requires a UA that identifies the application.
        return httpx.AsyncClient(
            timeout=70.0,
            follow_redirects=True,
            headers={"User-Agent": settings.HTTP_USER_AGENT},
        )

    async def geocode(self, location: str, country_code: str | None = None) -> tuple[float, float] | None:
        key = f"{location}|{country_code or ''}".lower()
        if key in self._geocode_cache:
            return self._geocode_cache[key]

        # Nominatim asks for no more than one request per second.
        elapsed = time.monotonic() - self._last_nominatim_at
        if elapsed < 1.1:
            await asyncio.sleep(1.1 - elapsed)

        params: dict[str, Any] = {"q": location, "format": "json", "limit": 1}
        if country_code:
            params["countrycodes"] = country_code.lower()
        try:
            async with self._client() as client:
                response = await client.get(NOMINATIM_URL, params=params)
            self._last_nominatim_at = time.monotonic()
            if response.status_code != 200:
                logger.warning("nominatim_error", status=response.status_code, location=location)
                self._geocode_cache[key] = None
                return None
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("nominatim_failed", location=location, error=str(exc))
            self._geocode_cache[key] = None
            return None

        if not payload:
            self._geocode_cache[key] = None
            return None
        point = (float(payload[0]["lat"]), float(payload[0]["lon"]))
        self._geocode_cache[key] = point
        return point

    async def search_area(
        self,
        *,
        location: str,
        industry_slug: str,
        country_code: str | None = None,
        limit: int = 60,
        radius_m: int = DEFAULT_RADIUS_M,
    ) -> list[PlaceResult]:
        """Return mapped businesses of one industry near one location."""
        filters = OSM_TAGS.get(industry_slug)
        if not filters:
            return []
        point = await self.geocode(location, country_code)
        if point is None:
            logger.info("overpass_skipped_no_geocode", location=location)
            return []

        lat, lon = point
        clauses = "\n  ".join(
            f'nwr(around:{radius_m},{lat},{lon}){tag_filter};' for tag_filter in filters
        )
        query = f"[out:json][timeout:60];\n(\n  {clauses}\n);\nout center tags {limit};"

        payload: dict[str, Any] | None = None
        async with self._client() as client:
            for mirror in OVERPASS_MIRRORS:
                try:
                    response = await client.post(mirror, data={"data": query})
                except httpx.HTTPError as exc:
                    logger.warning("overpass_unreachable", mirror=mirror, error=type(exc).__name__)
                    continue
                if response.status_code == 200:
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = None
                    if payload is not None:
                        break
                # 429/504 mean the mirror is busy; move to the next one.
                logger.warning("overpass_mirror_busy", mirror=mirror, status=response.status_code)

        if payload is None:
            logger.warning("overpass_all_mirrors_failed", location=location)
            return []

        results: list[PlaceResult] = []
        for element in payload.get("elements", []):
            tags = element.get("tags") or {}
            name = (tags.get("name") or "").strip()
            if not name:
                continue  # an unnamed node is not a usable prospect
            element_type = element.get("type", "node")
            element_id = element.get("id")
            centre = element.get("center") or {}
            results.append(
                PlaceResult(
                    name=name[:300],
                    website=(tags.get("website") or tags.get("contact:website") or "").strip(),
                    phone=(tags.get("phone") or tags.get("contact:phone") or "").strip(),
                    street=" ".join(
                        p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p
                    ),
                    city=(tags.get("addr:city") or "").strip(),
                    postal_code=(tags.get("addr:postcode") or "").strip(),
                    country_code=(tags.get("addr:country") or country_code or "").upper()[:2],
                    latitude=element.get("lat") or centre.get("lat"),
                    longitude=element.get("lon") or centre.get("lon"),
                    category=(
                        tags.get("craft") or tags.get("shop") or tags.get("office")
                        or tags.get("amenity") or tags.get("healthcare") or ""
                    ),
                    source="OpenStreetMap",
                    source_url=f"https://www.openstreetmap.org/{element_type}/{element_id}",
                    raw={k: v for k, v in tags.items() if len(str(v)) < 300},
                )
            )
        logger.info(
            "overpass_results", location=location, industry=industry_slug, count=len(results)
        )
        return results


overpass_connector = OverpassConnector()
