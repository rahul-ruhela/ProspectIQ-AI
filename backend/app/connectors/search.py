"""Concrete search connectors used by the Business Discovery agent."""
from __future__ import annotations

import urllib.parse
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.connectors.base import SearchConnector, SearchResult
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _client(timeout: float | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout or settings.HTTP_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": settings.HTTP_USER_AGENT},
    )


class SerperConnector(SearchConnector):
    """Google results via serper.dev. Paid, highest quality, used first when present."""

    slug = "serper"
    name = "Serper (Google Search API)"
    requires_api_key = True
    cost_per_call_usd = 0.001

    @property
    def available(self) -> bool:
        return bool(settings.SERPER_API_KEY)

    @property
    def unavailable_reason(self) -> str:
        return "SERPER_API_KEY is not set."

    async def search(
        self, query: str, *, limit: int = 20, country: str | None = None
    ) -> list[SearchResult]:
        if not self.available:
            return []
        payload: dict[str, Any] = {"q": query, "num": min(limit, 100)}
        if country:
            payload["gl"] = country.lower()
        async with _client() as client:
            response = await client.post(
                "https://google.serper.dev/search",
                json=payload,
                headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
            )
            response.raise_for_status()
            body = response.json()

        results: list[SearchResult] = []
        for rank, item in enumerate(body.get("organic", [])[:limit], start=1):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    source=self.name,
                    rank=rank,
                    raw=item,
                )
            )
        return results


class GoogleCSEConnector(SearchConnector):
    """Google Programmable Search. Official API, 100 free queries/day."""

    slug = "google_cse"
    name = "Google Programmable Search"
    requires_api_key = True
    cost_per_call_usd = 0.005

    @property
    def available(self) -> bool:
        return bool(settings.GOOGLE_CSE_KEY and settings.GOOGLE_CSE_CX)

    @property
    def unavailable_reason(self) -> str:
        return "GOOGLE_CSE_KEY and GOOGLE_CSE_CX must both be set."

    async def search(
        self, query: str, *, limit: int = 20, country: str | None = None
    ) -> list[SearchResult]:
        if not self.available:
            return []
        results: list[SearchResult] = []
        async with _client() as client:
            # The CSE API returns at most 10 results per call.
            for start in range(1, min(limit, 50) + 1, 10):
                params: dict[str, Any] = {
                    "key": settings.GOOGLE_CSE_KEY,
                    "cx": settings.GOOGLE_CSE_CX,
                    "q": query,
                    "start": start,
                    "num": 10,
                }
                if country:
                    params["gl"] = country.lower()
                response = await client.get(
                    "https://www.googleapis.com/customsearch/v1", params=params
                )
                if response.status_code != 200:
                    logger.warning("google_cse_error", status=response.status_code)
                    break
                items = response.json().get("items", [])
                if not items:
                    break
                for offset, item in enumerate(items):
                    results.append(
                        SearchResult(
                            title=item.get("title", ""),
                            url=item.get("link", ""),
                            snippet=item.get("snippet", ""),
                            source=self.name,
                            rank=start + offset,
                            raw=item,
                        )
                    )
                if len(results) >= limit:
                    break
        return results[:limit]


class SearxngConnector(SearchConnector):
    """Self-hosted SearXNG meta-search. Free and unmetered when the operator runs one."""

    slug = "searxng"
    name = "SearXNG (self-hosted)"

    @property
    def available(self) -> bool:
        return bool(settings.SEARXNG_URL)

    @property
    def unavailable_reason(self) -> str:
        return "SEARXNG_URL is not set."

    async def search(
        self, query: str, *, limit: int = 20, country: str | None = None
    ) -> list[SearchResult]:
        if not self.available:
            return []
        params: dict[str, Any] = {"q": query, "format": "json", "categories": "general"}
        if country:
            params["language"] = country.lower()
        async with _client() as client:
            response = await client.get(
                settings.SEARXNG_URL.rstrip("/") + "/search", params=params
            )
            response.raise_for_status()
            body = response.json()
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                source=self.name,
                rank=rank,
                raw=item,
            )
            for rank, item in enumerate(body.get("results", [])[:limit], start=1)
        ]


class DuckDuckGoConnector(SearchConnector):
    """Keyless fallback that parses the DuckDuckGo HTML endpoint.

    Rate limited and best-effort. It exists so a fresh install can discover real
    companies before the operator buys a search API key.
    """

    slug = "duckduckgo"
    name = "DuckDuckGo HTML"

    @property
    def available(self) -> bool:
        return bool(settings.ENABLE_DUCKDUCKGO)

    @property
    def unavailable_reason(self) -> str:
        return "ENABLE_DUCKDUCKGO is false."

    async def search(
        self, query: str, *, limit: int = 20, country: str | None = None
    ) -> list[SearchResult]:
        if not self.available:
            return []
        data = {"q": query}
        if country:
            data["kl"] = f"{country.lower()}-{country.lower()}"
        async with _client() as client:
            response = await client.post(
                "https://html.duckduckgo.com/html/",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.status_code != 200:
                logger.warning("duckduckgo_error", status=response.status_code)
                return []
            html = response.text

        soup = BeautifulSoup(html, "lxml")
        results: list[SearchResult] = []
        for rank, node in enumerate(soup.select("div.result")[:limit], start=1):
            link = node.select_one("a.result__a")
            if not link:
                continue
            url = self._clean_url(link.get("href", ""))
            if not url:
                continue
            snippet_node = node.select_one(".result__snippet")
            results.append(
                SearchResult(
                    title=link.get_text(strip=True),
                    url=url,
                    snippet=snippet_node.get_text(strip=True) if snippet_node else "",
                    source=self.name,
                    rank=rank,
                )
            )
        return results

    @staticmethod
    def _clean_url(href: str) -> str:
        """DuckDuckGo wraps outbound links in a redirector; unwrap to the real URL."""
        if not href:
            return ""
        if href.startswith("//duckduckgo.com/l/") or "/l/?uddg=" in href:
            parsed = urllib.parse.urlparse(href if href.startswith("http") else "https:" + href)
            target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
            return urllib.parse.unquote(target)
        if href.startswith("//"):
            return "https:" + href
        return href


ALL_CONNECTORS: list[SearchConnector] = [
    SerperConnector(),
    GoogleCSEConnector(),
    SearxngConnector(),
    DuckDuckGoConnector(),
]


def available_connectors() -> list[SearchConnector]:
    """Connectors in preference order: paid/high-quality first, free fallback last."""
    return [c for c in ALL_CONNECTORS if c.available]


def connector_statuses() -> list[dict[str, Any]]:
    """Health of every discovery source, mapped directories included."""
    from app.connectors.places import google_places_connector, overpass_connector

    sources = [google_places_connector, overpass_connector, *ALL_CONNECTORS]
    return [
        {"slug": c.slug, "name": c.name, "available": c.available, "reason": c.status().reason}
        for c in sources
    ]
