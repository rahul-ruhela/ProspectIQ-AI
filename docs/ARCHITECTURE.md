# Architecture

## The idea

A sales department is a set of specialists coordinated by a manager. ProspectIQ models
that literally: fifteen agents, each with one job, a declared input and output schema,
its own tools, and a confidence score on every result. The CEO Orchestrator plans the
work, assigns it, watches it and combines it.

The constraint that shapes everything else: **the platform may not state anything it
cannot attribute.** That is not a prompt instruction — it is enforced in the schema, in
the extraction rules, and in the UI.

---

## Request lifecycle: one click to prospects

```
POST /campaigns/{id}/start
        │
        ├── validates targeting, refuses a job with no country
        ├── creates ResearchJob(status=queued)
        └── dispatch_job() ──► Celery `research` queue ──► worker
                                          │
                                          ▼
                            CEOOrchestratorAgent.execute()
                                          │
        ┌─────────────────────────────────┴──────────────────────────────┐
        │ 1. plan()          brief → strategy (cheap model, or rules)     │
        │ 2. GlobalSearch    filters → localised query plan               │
        │ 3. BusinessDiscovery  queries → real companies + source URLs    │
        └─────────────────────────────────┬──────────────────────────────┘
                                          │  for each company:
                                          ▼
   WebsiteScraping → TechnologyDetection → WebsiteIntelligence → CompanyVerification
        │                                                              │
        │                              (rejected? stop spending here) ─┘
        ▼
   DecisionMaker → ContactEnrichment → EmailVerification → PhoneIntelligence
        │
        ▼
   BuyingSignal → AIOpportunity → LeadQuality → OpportunityScoring
        │
        ▼
   qualified?  ──yes──►  build_report()  →  PipelineEntry(stage=qualified)
        │
        └──no───────►  PipelineEntry(stage=discovered), rejection reason recorded
```

Progress, counters and cost are committed after every company, so the UI tracks a live
job and a lost worker never loses completed work. The orchestrator re-reads
`cancel_requested` between companies, which is how pause and cancel stop cleanly.

---

## The agent contract

Every AI employee subclasses `BaseAgent`:

```python
class BaseAgent(ABC):
    key: str                      # stable identifier, also the DB primary key
    display_name: str
    role: str                     # what this employee is
    goal: str                     # what it is accountable for
    tools: tuple[str, ...]        # what it is allowed to use
    model_tier: str               # "cheap" | "smart"
    input_schema: dict            # JSON Schema, surfaced in the UI
    output_schema: dict
    max_attempts: int

    async def run(self, ctx: AgentContext, payload: dict) -> AgentResult: ...
```

`execute()` wraps `run()` and is where the observability comes from:

- creates an `AgentTask` row and an `AgentExecution` row per attempt
- retries up to `max_attempts`, recording each failure
- times the call and accumulates tokens, USD and HTTP request counts
- updates the agent's rolling averages (duration, confidence, failure count)
- catches every exception — **one agent failing never takes down the department**
- honours the admin's enable/disable toggle

`AgentContext` carries the session, the tenant, the current job and company, the LLM
client and the running usage totals. `ctx.for_company()` narrows it per company so logs
and costs attribute correctly.

Agents talk to each other only through `self.send()`, which writes an `AgentMessage` —
the bus is inspectable in the UI rather than implicit in call order.

---

## Data model

48 tables. The important structural decision is `ProvenanceMixin`, attached to every
table that stores a claim about the outside world:

| Column | Meaning |
|---|---|
| `source` | Human-readable origin — "OpenStreetMap", "Company website (about)" |
| `source_url` | The exact page the value came from |
| `confidence` | 0.0–1.0 |
| `verification_status` | `verified` / `needs_verification` / `unknown` / `rejected` |
| `last_verified_at` | When it was last confirmed |

Tables carrying it: `companies`, `company_sources`, `company_locations`, `websites`,
`website_features`, `technologies`, `contacts`, `decision_makers`, `buying_signals`,
`research_findings`.

Inference is separated from observation by the `Certainty` enum — `observed`, `likely`,
`possible`, `unknown`. "No CRM was detected in the page markup" is `likely`, not
`observed`, because a server-side CRM is invisible to a crawler. The UI renders that
badge next to the claim.

### Groups

| Group | Tables |
|---|---|
| Tenancy & access | `organizations`, `users`, `roles`, `permissions`, `role_permissions`, `audit_logs` |
| Geography & taxonomy | `countries`, `regions`, `cities`, `industries` |
| Campaigns | `campaigns`, `campaign_filters`, `research_jobs` |
| Companies | `companies`, `company_sources`, `company_locations`, `company_verifications` |
| Web intelligence | `websites`, `website_pages`, `website_features`, `technologies` |
| People & contact | `decision_makers`, `contacts`, `email_verifications`, `phone_verifications` |
| Signals & scoring | `buying_signals`, `opportunity_scores` |
| Research output | `ai_research`, `research_findings`, `evidence` |
| Agent runtime | `agents`, `agent_tasks`, `agent_executions`, `agent_messages`, `agent_logs`, `ai_memory` |
| CRM | `pipeline_entries`, `activities`, `human_feedback` |
| Admin & cost | `ai_providers`, `ai_models`, `api_keys`, `connectors`, `scoring_rules`, `service_catalog`, `ai_usage`, `cost_tracking`, `exports` |

---

## Discovery

Connectors are ordered by how well attributed their output is:

1. **Mapped directories** (OpenStreetMap via Overpass). Structured records — name,
   website, phone, address — already tied to a citable element URL. Keyless. Runs first.
   Needs a city, because Overpass searches around a geocoded point.
2. **Search connectors** (Serper → Google CSE → SearXNG → DuckDuckGo). Broader reach,
   weaker attribution: a title and a snippet.

Results from aggregator domains (Yelp, LinkedIn, directories) never become a company on
their own. They are held back and used to *corroborate* a company discovered elsewhere,
which raises its confidence — independent sources are the signal that something is real.

If no connector is available, discovery fails loudly with the reason. It never returns
plausible-looking placeholders.

---

## Crawling

`Fetcher` is per-site so robots.txt and pacing are per-host: it parses `robots.txt`
once, enforces `CRAWL_DELAY_SECONDS` between requests to the same host, and identifies
itself. `crawl_site` ranks discovered internal links by page type so a 12-page budget
buys the most sales signal — about, services, contact, team, pricing, booking, careers
— rather than the first twelve links.

Client-rendered sites produce almost no text. Rather than call them fake, the
verification agent marks them `needs_verification` and says the site is probably
JavaScript-rendered. Enabling Playwright makes them readable.

---

## Extraction: why it is conservative

Extraction heuristics were tightened against real websites. Each rule below exists
because its absence produced a wrong fact:

- **People.** A candidate must look like a personal name *and* sit next to something
  that reads like a job title (short, not a paragraph). A title-cased marketing heading
  like "Maintenance Between Cleanings" matched the shape of a name and, next to body
  copy containing a role word, became a fake decision maker. Now a stoplist of business
  words rejects the name, and a length/shape check rejects the title.
- **Buying signals.** Phrases match on word boundaries and generic single words were
  removed — "we raised the bar for service" was becoming a funding event. Legal and FAQ
  pages are excluded because policy wording trips the patterns. The stored title quotes
  the matched phrase, so a human can judge it.
- **Emails.** Asset filenames (`logo@2x.png`) and placeholder domains are filtered.
  Consumer mailbox providers are classified `personal`, role addresses `role`, and only
  same-domain non-role addresses `business`.
- **Verification.** DNS failure yields `needs_verification`, not `invalid` — the network
  may be at fault, and a false negative is still a wrong fact.

The tests in `backend/tests/test_data_quality.py` pin each of these cases.

---

## Scoring

Deterministic and explainable. Nine components, each normalised to 0–1, multiplied by an
admin-tunable weight, with the reasons stored alongside the number:

```python
ComponentScore(key="lead_opportunity", normalised=0.75, weight=15.0,
               reasons=["Missing lead capture: contact form, quote request, live chat."])
```

`stamp_score` writes the total, the category, every component and the full breakdown to
`opportunity_scores`, and the UI renders the reasoning. The admin endpoint refuses a
weight change that would break the 100-point total, so the score always stays on a
0–100 scale.

---

## Reports

`build_report` assembles the deterministic report first — summary, acquisition channels,
problems, why to contact, talking points, objections, email draft, call script — from
observed facts alone. Findings and evidence rows are written for every claim.

Only then, and only if the company already scored ≥ 60, is the smart model asked to
*phrase* what is established. It receives the structured observations and the crawled
text, and is instructed to write "Unknown" rather than fill a gap. If the call fails or
no key is configured, the deterministic report stands. **The LLM is never the source of
a fact.**

---

## Cost control

- Cheap model for planning, smart model only for qualified prospects
- Every call writes an `ai_usage` row with tokens and USD
- Campaigns stop when `spent_usd` exceeds `budget_usd`
- Verification-rejected companies stop consuming budget immediately
- A nightly task rolls usage into `cost_tracking` with cost-per-prospect

---

## Frontend

Vite + React 19 + TypeScript, Tailwind with CSS-variable theming (light/dark both
explicitly designed), React Query for server state, Zustand for auth and theme.

`src/api/types.ts` mirrors the backend schemas so a contract change surfaces at compile
time. The axios client attaches the token, refreshes on 401, and collapses concurrent
refreshes into one.

Charts use a validated palette: categorical hues assigned in fixed order, single-hue
ordinal ramps for ordered magnitudes, and separately chosen light and dark steps rather
than an automatic flip.

The provenance components (`<Provenance>`, `<VerificationBadge>`, `<CertaintyBadge>`,
`<ValueOrUnknown>`) are used everywhere a fact is displayed — an unverifiable value
renders as an explicit italic "Unknown" rather than a blank that reads as data.
