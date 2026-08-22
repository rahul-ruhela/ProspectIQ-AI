"""HTML parsing helpers: page classification, contact extraction and people extraction.

Everything here is evidence-first — each returned item records the URL it came from
and the exact text that justified it.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup

EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}",
)
PHONE_RE = re.compile(
    r"(?:(?:\+|00)\d{1,3}[\s.\-]?)?(?:\(\d{1,4}\)[\s.\-]?)?\d{2,4}[\s.\-]?\d{2,4}[\s.\-]?\d{0,4}"
)
YEAR_RE = re.compile(r"(?:©|&copy;|copyright)[^0-9]{0,20}((?:19|20)\d{2})", re.IGNORECASE)

# Page-type detection is URL-first (cheap, reliable) with a text fallback.
# Order matters: the first match wins, so the narrow types come before the broad
# ones. "legal" leads because "/terms-of-service" contains "service".
PAGE_TYPE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("legal", ("privacy", "terms", "cookie", "legal", "gdpr", "disclaimer")),
    ("about", ("about", "who-we-are", "our-story", "company")),
    ("services", ("service", "solution", "what-we-do", "offering")),
    ("products", ("product", "shop", "store", "catalog")),
    ("pricing", ("pricing", "price", "plans", "rates", "quote")),
    ("contact", ("contact", "get-in-touch", "reach-us", "locations")),
    ("booking", ("book", "appointment", "schedule", "reservation", "calendar")),
    ("careers", ("career", "jobs", "join-us", "hiring", "vacanc", "work-with-us")),
    ("blog", ("blog", "news", "insight", "article", "press")),
    ("faq", ("faq", "help", "support", "knowledge")),
    ("team", ("team", "leadership", "management", "our-people", "staff")),
    ("portal", ("portal", "login", "account", "signin", "sign-in", "client-area")),
]

ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "founder": ("founder", "co-founder", "cofounder"),
    "owner": ("owner", "proprietor", "principal"),
    "ceo": ("ceo", "chief executive"),
    "president": ("president",),
    "coo": ("coo", "chief operating"),
    "managing_director": ("managing director", "general manager", "md"),
    "marketing_director": ("marketing director", "head of marketing", "cmo", "marketing manager"),
    "it_director": ("it director", "cto", "head of technology", "it manager", "chief technology"),
    "sales_director": ("sales director", "head of sales", "vp sales", "sales manager"),
}

SENIORITY_BY_ROLE: dict[str, str] = {
    "founder": "founder",
    "owner": "owner",
    "ceo": "c_level",
    "president": "c_level",
    "coo": "c_level",
    "it_director": "c_level",
    "managing_director": "executive",
    "marketing_director": "director",
    "sales_director": "director",
}

# A name token: a capitalised word that may carry an internal capital ("McDonald")
# or a hyphen/apostrophe with its own capital ("Mary-Ann", "O'Neill"), optionally
# followed by a full stop. All-caps shouting ("HVAC") never matches.
_NAME_TOKEN = r"[A-Z][a-z]*(?:[A-Z][a-z]+)*(?:['’-][A-Z]?[a-z]+)*\.?"
NAME_RE = re.compile(rf"^{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{1,2}}$")

# Title-cased headings are common on marketing pages ("Maintenance Between Cleanings"),
# and they match the shape of a person's name. A candidate containing any of these
# tokens is a phrase, not a person, so it is never stored as a decision maker.
NON_NAME_TOKENS = {
    "service", "services", "repair", "repairs", "cleaning", "cleanings", "maintenance",
    "installation", "install", "solution", "solutions", "company", "companies", "team",
    "about", "contact", "home", "quality", "customer", "customers", "client", "clients",
    "free", "quote", "estimate", "emergency", "commercial", "residential", "system",
    "systems", "air", "heating", "cooling", "plumbing", "electrical", "duct", "ducts",
    "why", "how", "what", "when", "where", "our", "your", "their", "the", "and", "with",
    "for", "from", "between", "more", "best", "new", "top", "get", "call", "now",
    "read", "learn", "view", "book", "schedule", "request", "privacy", "terms",
    "reviews", "review", "testimonial", "testimonials", "blog", "news", "faq", "help",
    "price", "pricing", "cost", "costs", "areas", "area", "city", "county", "state",
    "inc", "llc", "ltd", "corp", "co", "group", "partners", "associates",
}

# A title must read like a job title, not a paragraph of body copy.
MAX_ROLE_TITLE_CHARS = 90


def looks_like_person_name(candidate: str) -> bool:
    """True only when every token could plausibly be part of a personal name."""
    if not NAME_RE.match(candidate):
        return False
    tokens = [t.strip(".'-").lower() for t in candidate.split()]
    if any(token in NON_NAME_TOKENS for token in tokens):
        return False
    # Initials are fine ("J. Smith"), single-letter words otherwise are not.
    return all(len(token) > 1 or candidate.count(".") for token in tokens)


def looks_like_role_title(text: str) -> bool:
    """A role line is short and leads with the role, not buried in prose."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) > MAX_ROLE_TITLE_CHARS:
        return False
    # Body copy reads as sentences; a title does not end in a full stop mid-thought.
    return cleaned.count(".") <= 1 and len(cleaned.split()) <= 12


ROLE_EMAIL_PREFIXES = {
    "info",
    "contact",
    "hello",
    "sales",
    "support",
    "admin",
    "office",
    "enquiries",
    "inquiries",
    "help",
    "team",
    "service",
    "bookings",
    "reception",
    "mail",
}

SKIP_EMAIL_DOMAINS = {"sentry.io", "example.com", "domain.com", "yourdomain.com", "email.com"}
SKIP_EMAIL_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")


@dataclass(slots=True)
class ExtractedEmail:
    value: str
    found_on_url: str
    context: str = ""
    is_role_account: bool = False


@dataclass(slots=True)
class ExtractedPhone:
    value: str
    found_on_url: str
    context: str = ""


@dataclass(slots=True)
class ExtractedPerson:
    full_name: str
    role_title: str
    role_category: str
    seniority: str
    found_on_url: str
    context: str = ""
    profile_url: str | None = None
    linkedin_url: str | None = None


@dataclass(slots=True)
class ParsedPage:
    url: str
    page_type: str
    title: str = ""
    meta_description: str = ""
    language: str = ""
    text: str = ""
    headings: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    internal_links: list[str] = field(default_factory=list)
    forms_count: int = 0
    form_fields: list[str] = field(default_factory=list)
    images: int = 0
    has_viewport_meta: bool = False
    copyright_year: int | None = None
    emails: list[ExtractedEmail] = field(default_factory=list)
    phones: list[ExtractedPhone] = field(default_factory=list)
    social_links: dict[str, str] = field(default_factory=dict)
    word_count: int = 0
    raw_html: str = ""


def classify_page(url: str, title: str = "") -> str:
    path = urllib.parse.urlparse(url).path.lower().strip("/")
    if not path:
        return "homepage"
    haystack = f"{path} {title.lower()}"
    for page_type, needles in PAGE_TYPE_PATTERNS:
        if any(needle in haystack for needle in needles):
            return page_type
    return "other"


def _is_plausible_email(value: str) -> bool:
    value = value.lower()
    if value.endswith(SKIP_EMAIL_EXTENSIONS):
        return False
    domain = value.rsplit("@", 1)[-1]
    if domain in SKIP_EMAIL_DOMAINS:
        return False
    # Hashed asset names such as name@2x.png style artefacts.
    return not re.match(r"^\d+x$", value.split("@")[-1].split(".")[0])


def _normalise_phone(raw: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", raw)
    return cleaned


def parse_page(url: str, html: str) -> ParsedPage:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = (meta_desc_tag.get("content") or "").strip() if meta_desc_tag else ""
    html_tag = soup.find("html")
    language = (html_tag.get("lang") or "").strip() if html_tag else ""

    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    headings = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"])][:40]

    base = urllib.parse.urlparse(url)
    links: list[str] = []
    internal: list[str] = []
    social: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urllib.parse.urljoin(url, href)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        clean = parsed._replace(fragment="").geturl()
        links.append(clean)
        if parsed.netloc == base.netloc:
            internal.append(clean)
        else:
            for network in ("linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com", "youtube.com"):
                if network in parsed.netloc and network not in social:
                    social[network] = clean

    forms = soup.find_all("form")
    form_fields = [
        (inp.get("name") or inp.get("type") or "").lower()
        for form in forms
        for inp in form.find_all(["input", "textarea", "select"])
    ]

    emails: list[ExtractedEmail] = []
    seen_emails: set[str] = set()
    for anchor in soup.select('a[href^="mailto:"]'):
        raw = anchor["href"][7:].split("?")[0].strip().lower()
        if raw and _is_plausible_email(raw) and raw not in seen_emails:
            seen_emails.add(raw)
            emails.append(
                ExtractedEmail(
                    value=raw,
                    found_on_url=url,
                    context=anchor.get_text(strip=True) or "mailto link",
                    is_role_account=raw.split("@")[0] in ROLE_EMAIL_PREFIXES,
                )
            )
    for match in EMAIL_RE.finditer(text):
        raw = match.group(0).lower()
        if raw in seen_emails or not _is_plausible_email(raw):
            continue
        seen_emails.add(raw)
        start = max(0, match.start() - 60)
        emails.append(
            ExtractedEmail(
                value=raw,
                found_on_url=url,
                context=text[start : match.end() + 40],
                is_role_account=raw.split("@")[0] in ROLE_EMAIL_PREFIXES,
            )
        )

    phones: list[ExtractedPhone] = []
    seen_phones: set[str] = set()
    for anchor in soup.select('a[href^="tel:"]'):
        raw = urllib.parse.unquote(anchor["href"][4:]).strip()
        normalised = _normalise_phone(raw)
        if len(normalised) >= 7 and normalised not in seen_phones:
            seen_phones.add(normalised)
            phones.append(
                ExtractedPhone(value=raw, found_on_url=url, context="tel: link")
            )

    year_match = YEAR_RE.search(html)
    copyright_year = int(year_match.group(1)) if year_match else None

    return ParsedPage(
        url=url,
        page_type=classify_page(url, title),
        title=title,
        meta_description=meta_description,
        language=language,
        text=text,
        headings=headings,
        links=links,
        internal_links=internal,
        forms_count=len(forms),
        form_fields=form_fields,
        images=len(soup.find_all("img")),
        has_viewport_meta=bool(soup.find("meta", attrs={"name": "viewport"})),
        copyright_year=copyright_year,
        emails=emails,
        phones=phones,
        social_links=social,
        word_count=len(text.split()),
        raw_html=html,
    )


def extract_people(page: ParsedPage) -> list[ExtractedPerson]:
    """Pull named decision makers out of a team/about page.

    Only returns a person when a real name and a real title sit next to each other in
    the document; anything less is left for a human to verify.
    """
    people: list[ExtractedPerson] = []
    seen: set[str] = set()
    soup = BeautifulSoup(page.raw_html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Strategy 1: structured team cards - a heading followed by a role line.
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "strong", "b"]):
        name = heading.get_text(" ", strip=True)
        if not looks_like_person_name(name):
            continue
        sibling_text = ""
        node = heading
        for _ in range(3):
            node = node.find_next(string=True)
            if node is None:
                break
            candidate = str(node).strip()
            if candidate and candidate != name:
                sibling_text = candidate
                break
        if not looks_like_role_title(sibling_text):
            continue
        role_category = _match_role(sibling_text)
        if not role_category:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        linkedin = None
        parent = heading.find_parent()
        if parent is not None:
            link = parent.find("a", href=re.compile(r"linkedin\.com/in/", re.I))
            if link:
                linkedin = urllib.parse.urljoin(page.url, link["href"])
        people.append(
            ExtractedPerson(
                full_name=name,
                role_title=sibling_text[:200],
                role_category=role_category,
                seniority=SENIORITY_BY_ROLE.get(role_category, "manager"),
                found_on_url=page.url,
                context=f"{name} - {sibling_text}"[:400],
                linkedin_url=linkedin,
            )
        )

    # Strategy 2: inline sentences such as "Jane Smith, Founder and CEO".
    for match in re.finditer(
        r"([A-Z][a-z'\-]+(?:\s+[A-Z][a-z'\-\.]+){1,2})\s*[,–—\-|]\s*([A-Za-z /&]{3,60})",
        page.text,
    ):
        name, title = match.group(1).strip(), match.group(2).strip()
        if name.lower() in seen or not looks_like_person_name(name):
            continue
        if not looks_like_role_title(title):
            continue
        role_category = _match_role(title)
        if not role_category:
            continue
        seen.add(name.lower())
        people.append(
            ExtractedPerson(
                full_name=name,
                role_title=title[:200],
                role_category=role_category,
                seniority=SENIORITY_BY_ROLE.get(role_category, "manager"),
                found_on_url=page.url,
                context=match.group(0)[:400],
            )
        )
    return people


def _match_role(text: str) -> str | None:
    lowered = text.lower()
    for category, needles in ROLE_KEYWORDS.items():
        for needle in needles:
            if needle == "md":
                if re.search(r"\bmd\b", lowered):
                    return category
            elif needle in lowered:
                return category
    return None


def summarise_site_text(pages: list[ParsedPage], limit: int = 6000) -> str:
    """Concatenate the most informative page text for LLM synthesis."""
    priority = ["homepage", "about", "services", "products", "pricing", "contact"]
    ordered = sorted(
        pages,
        key=lambda p: priority.index(p.page_type) if p.page_type in priority else len(priority),
    )
    chunks: list[str] = []
    used = 0
    for page in ordered:
        if used >= limit:
            break
        excerpt = page.text[: max(0, min(1500, limit - used))]
        if not excerpt:
            continue
        chunks.append(f"[{page.page_type}] {page.url}\n{excerpt}")
        used += len(excerpt)
    return "\n\n".join(chunks)


def as_evidence(page: ParsedPage, needle: str, window: int = 160) -> dict[str, Any]:
    """Return an evidence payload proving `needle` appears on `page`."""
    index = page.text.lower().find(needle.lower())
    excerpt = ""
    if index >= 0:
        start = max(0, index - window // 2)
        excerpt = page.text[start : index + len(needle) + window // 2]
    return {"url": page.url, "excerpt": excerpt, "found": index >= 0}
