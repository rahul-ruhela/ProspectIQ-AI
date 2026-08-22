"""Polite HTTP fetching: robots.txt, rate limiting and an optional Playwright fallback."""
from __future__ import annotations

import asyncio
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class FetchedPage:
    url: str
    final_url: str = ""
    status: int = 0
    html: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    elapsed_ms: int = 0
    error: str | None = None
    rendered: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and bool(self.html)


class Fetcher:
    """One instance per crawled site so robots and pacing are per-host."""

    def __init__(self, *, respect_robots: bool | None = None, delay: float | None = None) -> None:
        self.respect_robots = (
            settings.RESPECT_ROBOTS_TXT if respect_robots is None else respect_robots
        )
        self.delay = settings.CRAWL_DELAY_SECONDS if delay is None else delay
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last_request_at: dict[str, float] = {}
        self.request_count = 0

    async def __aenter__(self) -> "Fetcher":
        self._client = httpx.AsyncClient(
            timeout=settings.HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={
                "User-Agent": settings.HTTP_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en;q=0.9,*;q=0.5",
            },
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urllib.parse.urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            self._robots[origin] = await self._load_robots(origin)
        parser = self._robots[origin]
        if parser is None:
            # No robots.txt (or unreadable) means no restriction.
            return True
        return parser.can_fetch(settings.HTTP_USER_AGENT, url)

    async def _load_robots(self, origin: str) -> urllib.robotparser.RobotFileParser | None:
        try:
            response = await self._client.get(f"{origin}/robots.txt", timeout=8.0)
        except httpx.HTTPError:
            return None
        if response.status_code != 200 or not response.text.strip():
            return None
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser

    async def _pace(self, host: str) -> None:
        last = self._last_request_at.get(host)
        if last is not None:
            wait = self.delay - (time.monotonic() - last)
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_request_at[host] = time.monotonic()

    async def get(self, url: str, *, allow_render: bool = True) -> FetchedPage:
        host = urllib.parse.urlparse(url).netloc
        if not await self.allowed(url):
            return FetchedPage(url=url, error="blocked_by_robots")

        await self._pace(host)
        started = time.monotonic()
        try:
            response = await self._client.get(url)
        except httpx.HTTPError as exc:
            return FetchedPage(url=url, error=type(exc).__name__)

        self.request_count += 1
        page = FetchedPage(
            url=url,
            final_url=str(response.url),
            status=response.status_code,
            html=response.text if "html" in response.headers.get("content-type", "") else "",
            headers={k.lower(): v for k, v in response.headers.items()},
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )

        if allow_render and settings.ENABLE_PLAYWRIGHT and self._needs_render(page):
            rendered = await self._render(url)
            if rendered is not None:
                page.html = rendered
                page.rendered = True
        return page

    @staticmethod
    def _needs_render(page: FetchedPage) -> bool:
        """A near-empty body on a 200 usually means a client-rendered SPA."""
        if not page.ok:
            return False
        body = page.html.lower()
        if "<noscript" in body and "enable javascript" in body:
            return True
        # Strip tags cheaply: an SPA shell has almost no visible text.
        visible = len(body) - body.count("<") * 12
        return visible < 1500

    async def _render(self, url: str) -> str | None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("playwright_not_installed")
            return None
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(args=["--no-sandbox"])
                context = await browser.new_context(user_agent=settings.HTTP_USER_AGENT)
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                html = await page.content()
                await browser.close()
                return html
        except Exception as exc:  # rendering is best-effort
            logger.warning("playwright_render_failed", url=url, error=str(exc))
            return None
