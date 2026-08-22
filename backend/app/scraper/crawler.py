"""Breadth-first site crawler that prioritises the pages sales intelligence needs."""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import get_logger
from app.scraper.extract import ParsedPage, classify_page, parse_page
from app.scraper.fetch import FetchedPage, Fetcher

logger = get_logger(__name__)

# Pages that carry the most sales signal, crawled before anything else.
PRIORITY_TYPES = (
    "homepage",
    "about",
    "services",
    "contact",
    "team",
    "pricing",
    "products",
    "booking",
    "careers",
    "blog",
    "faq",
    "portal",
)
SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip", ".mp4",
    ".mp3", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".css", ".js",
)


@dataclass(slots=True)
class CrawlResult:
    url: str
    final_url: str = ""
    reachable: bool = False
    http_status: int | None = None
    is_https: bool = False
    load_time_ms: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    pages: list[ParsedPage] = field(default_factory=list)
    homepage_html: str = ""
    error: str | None = None
    requests_made: int = 0

    def page_types(self) -> set[str]:
        return {p.page_type for p in self.pages}

    def page_by_type(self, page_type: str) -> ParsedPage | None:
        for page in self.pages:
            if page.page_type == page_type:
                return page
        return None


def normalise_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw.lstrip("/")
    parsed = urllib.parse.urlparse(raw)
    if not parsed.netloc:
        return ""
    return parsed._replace(fragment="", query="").geturl().rstrip("/")


def domain_of(raw: str) -> str:
    parsed = urllib.parse.urlparse(normalise_url(raw))
    host = parsed.netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _should_follow(url: str, root_netloc: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.replace("www.", "") != root_netloc.replace("www.", ""):
        return False
    path = parsed.path.lower()
    if path.endswith(SKIP_EXTENSIONS):
        return False
    # Skip obvious crawl traps.
    return not any(trap in path for trap in ("/tag/", "/category/", "/author/", "/feed", "/wp-json"))


async def crawl_site(url: str, *, max_pages: int | None = None) -> CrawlResult:
    """Fetch a site's key pages and return parsed content plus reachability facts."""
    root = normalise_url(url)
    result = CrawlResult(url=root)
    if not root:
        result.error = "invalid_url"
        return result

    budget = max_pages or settings.CRAWL_MAX_PAGES_PER_SITE
    root_netloc = urllib.parse.urlparse(root).netloc

    async with Fetcher() as fetcher:
        home: FetchedPage = await fetcher.get(root)
        if not home.ok and home.status in (0, 301, 302, 403, 404) and root.startswith("https://"):
            # Some small-business hosts still serve only over http.
            home = await fetcher.get("http://" + root[len("https://") :])

        result.http_status = home.status or None
        result.error = home.error
        result.load_time_ms = home.elapsed_ms
        result.headers = home.headers
        result.final_url = home.final_url or root
        result.is_https = str(result.final_url).startswith("https://")

        if not home.ok:
            result.reachable = False
            result.requests_made = fetcher.request_count
            return result

        result.reachable = True
        result.homepage_html = home.html
        homepage = parse_page(home.final_url or root, home.html)
        homepage.page_type = "homepage"
        result.pages.append(homepage)

        # Rank the discovered internal links so the crawl budget buys the most signal.
        candidates: dict[str, tuple[int, str]] = {}
        for link in homepage.internal_links:
            if not _should_follow(link, root_netloc) or link.rstrip("/") == root:
                continue
            page_type = classify_page(link)
            rank = PRIORITY_TYPES.index(page_type) if page_type in PRIORITY_TYPES else 99
            existing = candidates.get(page_type)
            if existing is None or rank < existing[0]:
                candidates[page_type] = (rank, link)

        queue = [link for _, (_, link) in sorted(candidates.items(), key=lambda kv: kv[1][0])]
        # Top up with any remaining internal links to fill the budget.
        for link in homepage.internal_links:
            if len(queue) >= budget * 2:
                break
            if link not in queue and _should_follow(link, root_netloc):
                queue.append(link)

        seen = {root, home.final_url}
        for link in queue:
            if len(result.pages) >= budget:
                break
            if link in seen:
                continue
            seen.add(link)
            fetched = await fetcher.get(link, allow_render=False)
            if not fetched.ok:
                continue
            result.pages.append(parse_page(fetched.final_url or link, fetched.html))

        result.requests_made = fetcher.request_count

    logger.info(
        "crawl_complete", url=root, pages=len(result.pages), requests=result.requests_made
    )
    return result
