# ProspectIQ AI

**An autonomous B2B customer-acquisition platform — a department of AI employees that
finds real businesses, researches them, and prepares a human for the sales conversation.**

ProspectIQ is not a scraping tool. It is a sales-intelligence platform built around two
rules that are enforced in the schema, the agents and the UI:

1. **No invented data.** Every stored fact carries a source, a source URL, a confidence
   score and a verification date. When something cannot be established it is stored as
   `unknown` or `needs_verification` — never guessed. A decision maker who is not named
   on the company's own pages stays Unknown.
2. **No automated outreach.** The platform prepares research, drafts, call scripts and
   contact details. A human approves and sends. Nothing leaves the platform on its own.

---

## What it does

```
Campaign brief  →  CEO Orchestrator  →  15 AI employees  →  scored prospects + reports  →  CRM  →  human outreach
```

A campaign says *who* to look for ("small HVAC businesses in Austin that need AI
automation"). One click hands it to the CEO Orchestrator, which builds a research
strategy and assigns work to the department:

| # | AI employee | What it establishes |
|---|---|---|
| 1 | **CEO Orchestrator** | Reads the brief, plans the strategy, assigns and monitors every task, combines results |
| 2 | **Global Search Agent** | Turns country/region/city/industry filters into a localised query plan |
| 3 | **Business Discovery Agent** | Finds real businesses via mapped directories and search, recording each source URL |
| 4 | **Website Scraping Agent** | Crawls homepage, about, services, pricing, contact, team, booking, careers, blog, FAQ — robots.txt-aware |
| 5 | **Technology Detection Agent** | Fingerprints CMS, frontend, CRM, booking, payments, analytics, chat — storing the exact matched signature |
| 6 | **Website Intelligence Agent** | Scores website quality and records every present *and absent* capability with evidence |
| 7 | **AI Opportunity Agent** | Turns observed gaps into concrete opportunities, labelled observed / likely / possible / unknown |
| 8 | **Decision Maker Agent** | Extracts founders, owners, CEOs, directors named on the company's own pages |
| 9 | **Contact Enrichment Agent** | Collects published business emails and phone numbers, with the page each appeared on |
| 10 | **Email Verification Agent** | Syntax, DNS/MX, disposable, free-provider and role-account classification |
| 11 | **Phone Intelligence Agent** | E.164 normalisation, country, line type, WhatsApp likelihood |
| 12 | **Buying Signal Agent** | Hiring, growth, new locations, new services, funding, tech adoption — each a quoted phrase from a real page |
| 13 | **Company Verification Agent** | Existence, live website, industry match, duplicates, parked/spam domains |
| 14 | **Lead Quality Agent** | Rejects dead sites, wrong industries, duplicates and low-confidence records |
| 15 | **Opportunity Scoring Agent** | An explainable 0–100 score across nine weighted components, with the reasoning for each |

Every qualified prospect gets a report answering: who they are, what they do, how they
acquire customers, what problems exist, which service fits, why to contact them — and
the evidence behind each claim.

---

## Quick start

### Docker (everything at once)

```bash
cp backend/.env.example backend/.env      # set SECRET_KEY and, optionally, API keys
docker compose up -d --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API + Swagger | http://localhost:8000/docs |
| Flower (worker queue) | http://localhost:5555 |

The backend container runs migrations and seeds reference data on start.

### Local development

**Backend**

```bash
cd backend
python -m venv venv
venv/Scripts/activate            # Windows;  source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env             # set SECRET_KEY, DATABASE_URL, SEED_ADMIN_*
alembic upgrade head
python -m app.seed.seeder
uvicorn app.main:app --reload
```

**Worker** (optional — the API can also run a job inline)

```bash
celery -A app.workers.celery_app.celery_app worker --loglevel=info -Q research,enrichment,default
celery -A app.workers.celery_app.celery_app beat --loglevel=info
```

**Frontend**

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

**Tests**

```bash
cd backend && pytest
```

---

## Does it work without any API keys?

Yes — and it says so plainly on the Settings page and in `/system/status`.

| Capability | Without keys | With keys |
|---|---|---|
| Business discovery | **OpenStreetMap (Overpass)** — keyless, returns structured business records (name, website, phone, address) with a citable element URL | Add `SERPER_API_KEY`, Google CSE or a SearXNG instance for open-web reach beyond mapped businesses |
| Website research | Full — first-party crawler | Same |
| Technology, contacts, verification, signals, scoring | Full — deterministic engines | Same |
| Report narrative | Rules engine: grounded, factual, less fluent | `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` enables synthesis, email drafts and call scripts |

The LLM is never the source of a fact. It is given the crawled text and the structured
findings and is instructed to answer "Unknown" rather than fill a gap.

---

## Architecture

```
frontend/          Vite + React 19 + TypeScript + Tailwind + React Query + Zustand + Recharts
backend/
  app/
    agents/        The 15 AI employees, the orchestrator and the registry
    api/v1/        Auth, campaigns, jobs, companies, agents, CRM, analytics, admin
    connectors/    Discovery sources (OpenStreetMap, Serper, Google CSE, SearXNG, DuckDuckGo)
    core/          Config, database, security, RBAC dependencies, logging
    llm/           Multi-provider client (Anthropic, OpenAI) with tiered models and per-call cost accounting
    models/        48 tables — every outward fact carries provenance
    scraper/       robots-aware fetcher, crawler, extractors, technology signatures
    schemas/       Pydantic request/response contracts
    services/      Scoring engine, report builder, research lifecycle
    workers/       Celery app, research tasks, scheduled maintenance
    seed/          Reference data (countries, industries, services) — zero fake prospects
```

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL (+pgvector) ·
Redis · Celery · httpx · BeautifulSoup · Playwright (optional) · Anthropic · OpenAI.

### Data model: provenance is structural

`ProvenanceMixin` is attached to every table that stores a claim about the outside
world — companies, sources, contacts, decision makers, technologies, website features,
buying signals, findings:

```python
source              # "OpenStreetMap", "Company website (about)", …
source_url          # the exact page
confidence          # 0.0 – 1.0
verification_status # verified | needs_verification | unknown | rejected
last_verified_at
```

Inferences additionally carry a `Certainty` of `observed`, `likely`, `possible` or
`unknown`, so an inference is never presented as an observation.

### Scoring

A deterministic 0–100 score. Weights are admin-tunable and must total 100:

| Component | Weight | Component | Weight |
|---|---|---|---|
| Industry fit | 15 | Technology readiness | 10 |
| Lead opportunity | 15 | Buying signals | 10 |
| AI fit | 15 | Service match | 10 |
| Company size | 10 | Data confidence | 5 |
| Website opportunity | 10 | | |

Every component stores the reasons that produced it, and the UI renders them — the
ranking is auditable, not a black box.

### Cost control

Cheap models plan; the expensive tier runs only on prospects that already scored ≥ 60
and passed the quality gate. Every call is written to `ai_usage` with tokens and USD, and
rolled up nightly into cost-per-prospect. Campaigns stop when their budget is exhausted.

---

## Security

- JWT access/refresh tokens; refresh rotation collapses concurrent 401s into one refresh
- bcrypt password hashing (12 rounds)
- Four roles — admin, researcher, sales_user, viewer — enforced by dependency on every route
- Provider API keys encrypted at rest (Fernet) and never returned in clear
- Append-only audit log for security-relevant actions
- Input validated by Pydantic; output schemas never re-validate stored values into a 500
- Containers run as a non-root user
- Crawler honours robots.txt, paces requests per host and identifies itself

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/INSTALL.md`](docs/INSTALL.md) | Full installation, configuration and deployment (AWS / Azure) |
| [`docs/API.md`](docs/API.md) | Endpoint reference and worked examples |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Agent contract, request lifecycle, schema map |
| `/docs` (running app) | Interactive Swagger UI |

---

## Licence

Proprietary. All rights reserved.
