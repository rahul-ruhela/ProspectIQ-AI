# Where ProspectIQ looks for prospects

Every company row in the database is created from a result a connector actually
returned, and the raw result is stored verbatim in `company_sources` as evidence.
Nothing is generated from the model's imagination. This document lists the sources
that are wired today, what each one is good for, what it costs, and how the raw
results are narrowed down to "businesses that need a website or app and can afford
to pay for one".

---

## 1. Sources wired today

### Primary discovery — these create company records

| Source | Slug | Key needed | Cost | What it returns |
|---|---|---|---|---|
| OpenStreetMap (Nominatim + Overpass) | `openstreetmap` | No | Free | Structured records: name, website, phone, address, opening hours |
| Serper (Google Search API) | `serper` | `SERPER_API_KEY` | ~$0.001/query, free credits on signup | Google organic results |
| Google Programmable Search | `google_cse` | `GOOGLE_CSE_KEY` + `GOOGLE_CSE_CX` | 100 queries/day free, then $5/1 000 | Google organic results |
| SearXNG (self-hosted) | `searxng` | `SEARXNG_URL` | Free if you run it | Meta-search across many engines |
| DuckDuckGo HTML | `duckduckgo` | No | Free, rate limited | Organic results, keyless fallback |

Search connectors are tried in preference order: `serper` → `google_cse` →
`searxng` → `duckduckgo`. OpenStreetMap runs *before* free-text search because its
records are already structured and attributed, so they need less cleanup.

**OpenStreetMap is the most valuable free source for this use case.** It covers 33
verticals out of the box (`OSM_TAGS` in `backend/app/connectors/places.py`) — HVAC,
plumbing, electrical, roofing, landscaping, dental, medical, veterinary, legal,
accounting, real estate, automotive, fitness, beauty, restaurants, hospitality,
logistics, IT services and more — inside a 25 km radius of any city you name. Its
killer feature for a web-services agency: an OSM business record often has a phone
and address but **no `website` tag**, which is the single strongest indicator that
a business has no web presence to speak of.

### Enrichment — these add detail to companies already found

| Source | What it does |
|---|---|
| First-party crawler | Fetches up to `CRAWL_MAX_PAGES_PER_SITE` pages, honours `robots.txt`, rate limited |
| Technology detection | Fingerprints CMS, ecommerce, analytics, chat, booking widgets |
| DNS / MX verification | Confirms the email domain resolves, without probing mailboxes |

### Directories that are read but never trusted as the business itself

Roughly 40 aggregator domains (`AGGREGATOR_DOMAINS` in
`backend/app/agents/discovery.py`) — Yelp, Yellow Pages, Facebook, LinkedIn,
Instagram, BBB, Angi, Houzz, Thumbtack, Trustpilot, TripAdvisor, Clutch,
GoodFirms, Checkatrade, Crunchbase, ZoomInfo, Manta, Hotfrog and the rest.

A hit on one of these is kept as a **corroborating source** — it raises confidence
that the business is real — but it never becomes a company record on its own,
because the page describes a business rather than being one. This is what stops
the database filling up with "Yelp — Best Plumbers in Austin" as if it were a
plumbing company.

---

## 2. How "needs a website or app" is decided

This is not guesswork against a directory listing. Each candidate goes through the
website and intelligence agents, and the opportunity is derived from what is
actually missing on the live site (`OPPORTUNITY_RULES` in
`backend/app/agents/signals.py`):

| What is missing | What it makes sellable |
|---|---|
| No website at all (OSM record with no `website` tag) | Website build — the strongest signal there is |
| Site unreachable, parked, or "coming soon" | Website build / rescue |
| No online booking | AI automation |
| No live chat | AI agents |
| No contact form | Lead generation |
| No quote request flow | Lead generation |
| No customer portal | **Custom web application** |
| No newsletter capture | Marketing automation |
| No case studies | Website redesign |
| No published pricing | Website redesign |
| Not mobile friendly / no HTTPS / slow | Website redesign |

The custom-web-app prospects you asked about surface mainly through the
**customer portal** and **online booking** rules: a business with real operational
volume and no self-service anything.

---

## 3. How "can pay $50+/month" is approximated

Be clear-eyed about this: **no public source publishes a business's software
budget.** Any tool claiming to filter directly on "willing to pay $50/month" is
inferring it. What this platform does is score *propensity to spend*, from evidence
it can actually cite:

**Signals that a business already spends money on software** — this is the
`technology_readiness` component (weight 10), fingerprinted from the live page markup:
- CRM or marketing tooling detected (+0.4) — the strongest evidence of an existing
  software budget line.
- Analytics or ad tracking detected (+0.3) — they already pay for measurement, and
  ad tracking means they are buying traffic today.
- Payments or online booking detected (+0.2) — they already transact online.
- A modern frontend stack — React, Next.js, Vue, Angular, Webflow (+0.1) — which
  indicates someone was paid recently.
- Nothing detected at all scores 0.15, not zero: a business with no commercial
  software still needs the work, it just has less proven willingness to pay.

**Signals that a business has the revenue to spend**
- Staff count, via the `company_size` curve. It peaks at 20–99 employees (1.0),
  stays strong at 5–19 (0.85), and deliberately *falls* above 250 (0.5 and down) —
  big companies have agencies already. Sole traders score 0.45.
- Hiring activity — `we're hiring`, `open positions`, `current openings` matched on
  their own site. A business recruiting can afford $50/month.
- Growth and expansion language — `new location`, `now open in`, `rapid growth`,
  `recently launched`, `funding round`.
- Multiple locations, from OSM and the site's own pages.

**Verticals with a high floor.** The industries in `OSM_TAGS` were chosen partly
because their average job value makes a $50–$500/month retainer trivially
justifiable: HVAC, plumbing, electrical, roofing, dental, legal, accounting,
veterinary, real estate.

These combine into `opportunity_score` (0–100) and an `opportunity_category`. The
honest framing: filter on `min_score` to get businesses that both *need* the work
and *show evidence of spending money*. Treat it as a ranked list to work through,
not as a verified budget field.

---

## 4. "Authentic businesses only"

Every candidate passes through `CompanyVerificationAgent`
(`backend/app/agents/quality.py`) before it counts as a real lead:

1. **Exists** — corroborated by more than one independent source URL.
2. **Live** — the website actually resolves and returns content.
3. **Not parked or spam** — checked against markers like `this domain is for sale`,
   `under construction`, `lorem ipsum`, `account suspended`, `sample page`.
4. **Not a duplicate** — deduplicated on normalised domain.
5. **On-industry** — matches the vertical you targeted, not a loose keyword hit.

Anything that fails is flagged `is_rejected` with a `rejection_reason` rather than
deleted, so you can audit what was thrown away and why. Add
`include_rejected=true` to see them.

---

## 5. Filtering the results

**API** — `GET /api/v1/companies` accepts:

| Parameter | Use |
|---|---|
| `q` | Free text across name, domain, description |
| `country_code` | ISO-2, e.g. `IN`, `US`, `AE` |
| `industry_slug` | Any slug from the industry registry |
| `category` | Opportunity band |
| `min_score` / `max_score` | 0–100 opportunity score — **the main budget-proxy filter** |
| `has_contact` | Only companies with a reachable contact |
| `campaign_id` | One research run |
| `include_rejected` | Show what verification threw out |
| `sort_by` / `sort_dir` | Rank the list |
| `page` / `page_size` | Up to 200 per page |

**CSV export** — the export endpoint takes `min_score` and returns a flat file for
a spreadsheet or CRM import.

A practical starting filter for your use case:

```
GET /api/v1/companies?min_score=60&has_contact=true&country_code=IN&sort_by=opportunity_score
```

Then narrow by `industry_slug` per outreach batch.

---

## 6. Sources worth adding next

Ranked by value for finding businesses that need web work:

1. **Google Places API** — the single biggest upgrade. Returns review counts,
   ratings, business status and, crucially, a `website` field that is empty for
   businesses with no site. $200/month free credit. Would slot in beside the
   existing `places.py` connector.
2. **Company registries** — India MCA, UK Companies House (free API), OpenCorporates.
   Gives incorporation date and registered address: real, verifiable businesses.
3. **Job boards** — hiring is the strongest "has budget" signal and is public.
4. **Wappalyzer / BuiltWith** — confirms what a business already pays for.
5. **Certificate transparency logs (crt.sh)** — free, and shows which domains have
   no HTTPS certificate at all.

---

## 7. Credential status — verified 2026-08-22

Each of these was tested against the live endpoint, not assumed.

| Credential | Status | Detail |
|---|---|---|
| `SERPER_API_KEY` | ✅ **Working** | HTTP 200, returns real organic results, 1 credit per query |
| `GOOGLE_CSE_KEY` | ✅ **Valid** | Key authenticates; connector still disabled pending `GOOGLE_CSE_CX` |
| `GOOGLE_CSE_CX` | ❌ **Empty** | Blocks the connector — see below |
| `GEMINI_API_KEY` | ⚠️ **Authenticates, no quota** | HTTP 429 `prepayment credits are depleted` on every model |

### `GOOGLE_CSE_CX` — the one thing you can fix yourself

Go to <https://programmablesearchengine.google.com>, create a search engine, turn
on **"Search the entire web"**, and copy the **Search engine ID** into
`GOOGLE_CSE_CX`. The key is already correct and verified; this is the only missing
piece. Free tier is 100 queries/day.

### Gemini — the project has no free-tier allowance

The corrected key authenticates properly through the `x-goog-api-key` header. Two
separate problems sit behind it:

1. **Gemini 2.5 model ids are retired for new projects.** `gemini-2.5-flash`,
   `-flash-lite` and `-pro` all return `404 — no longer available to new users`,
   even though `ListModels` still lists them. The 3.x flash tiers replace them, so
   the configured models are now `gemini-3.5-flash-lite` (cheap) and
   `gemini-3.5-flash` (smart).
2. **Every 3.x model returns `429 RESOURCE_EXHAUSTED — "Your prepayment credits are
   depleted"`.** This is not a daily free-tier ceiling that resets overnight. The
   AI Studio project behind this key (`89788847888`) is on prepaid billing with a
   zero balance, so there is no free allowance to fall back on.

**This cannot be fixed from the codebase.** The options are to issue a key from an
AI Studio project that still has free-tier access, or to load prepaid credits —
which is the spend you asked to avoid. Until then `LLM_FREE_TIER_ONLY=true` keeps
the Anthropic and OpenAI keys unreachable, so nothing bills silently.

### What runs today without any of that

Discovery is live on **OpenStreetMap**, **Serper** and **DuckDuckGo**. Scoring,
verification, signal detection and opportunity rules are all deterministic — they
never needed the LLM. The only thing you lose without Gemini is narrative report
synthesis, which falls back to the rules engine.
