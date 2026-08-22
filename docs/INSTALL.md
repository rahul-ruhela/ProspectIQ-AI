# Installation and deployment

## Requirements

| Component | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.12 recommended (the container image) |
| Node.js | 20+ | 22 recommended |
| PostgreSQL | 14+ | 16 with the `pgvector` extension recommended |
| Redis | 6+ | Celery broker and result backend |
| Docker | 24+ | Optional, for the one-command path |

---

## Option A — Docker Compose

```bash
git clone <your-repo> prospectiq && cd prospectiq
cp backend/.env.example backend/.env
```

Edit `backend/.env` and set at minimum:

```dotenv
SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(48))">
SEED_ADMIN_EMAIL=you@yourcompany.com
SEED_ADMIN_PASSWORD=<at least 10 characters>
```

Then:

```bash
docker compose up -d --build
docker compose logs -f backend        # watch migrations + seeding
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| Flower | http://localhost:5555 |

**Port already in use?** A native PostgreSQL on the host will shadow the container's
published port. Put `POSTGRES_PORT=55432` in a root `.env` and point
`DATABASE_URL` at it for host-side tooling.

Useful commands:

```bash
docker compose ps                                   # service health
docker compose logs -f worker                       # research execution
docker compose exec backend alembic upgrade head    # re-run migrations
docker compose exec backend python -m app.seed.seeder
docker compose down -v                              # stop and wipe volumes
```

---

## Option B — Local development

### 1. Infrastructure

```bash
docker compose up -d postgres redis
```

Or use your own PostgreSQL and Redis and set `DATABASE_URL` / `REDIS_URL` accordingly.

### 2. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
cp .env.example .env             # then edit it
alembic upgrade head
python -m app.seed.seeder
uvicorn app.main:app --reload
```

Seeding is idempotent — safe to run whenever reference data changes.

### 3. Workers

Research jobs run in Celery. Without a worker, start a job with `run_inline: true` and
the API process will run it synchronously (development only — it blocks a request).

```bash
celery -A app.workers.celery_app.celery_app worker --loglevel=info -Q research,enrichment,default
celery -A app.workers.celery_app.celery_app beat --loglevel=info     # scheduled maintenance
celery -A app.workers.celery_app.celery_app flower --port=5555       # queue UI
```

On Windows, add `--pool=solo` to the worker command.

### 4. Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### 5. Optional: JavaScript rendering

Some sites render entirely client-side. To read them:

```bash
python -m playwright install chromium
# then set ENABLE_PLAYWRIGHT=true in backend/.env
```

Without it, such sites are marked `needs_verification` with a note explaining why —
they are never labelled fake.

---

## Configuration reference

### Required

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL DSN. `postgres://` and `postgresql://` are normalised to the psycopg driver |
| `REDIS_URL` | Celery broker and result backend |
| `SECRET_KEY` | JWT signing. **Must** be replaced before any deployment |

### Security

| Variable | Default | Purpose |
|---|---|---|
| `ENCRYPTION_KEY` | derived from `SECRET_KEY` | Fernet key for provider API keys at rest. Set explicitly in production so rotating `SECRET_KEY` does not orphan stored keys |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `14` | Refresh token lifetime |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Comma-separated allowed origins |

Generate an encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Discovery connectors

| Variable | Effect |
|---|---|
| `ENABLE_OPENSTREETMAP` | Keyless structured business records for mapped verticals. On by default |
| `SERPER_API_KEY` | Google results via serper.dev. Best open-web reach |
| `GOOGLE_CSE_KEY` + `GOOGLE_CSE_CX` | Google Programmable Search |
| `SEARXNG_URL` | Your own SearXNG instance |
| `ENABLE_DUCKDUCKGO` | Keyless HTML fallback. Frequently rate-limited; treat as best-effort |

Preference order for search is Serper → Google CSE → SearXNG → DuckDuckGo. Mapped
directories always run first, because their records arrive already attributed.

Check what is live at any time: `GET /system/status`, or the Settings page.

### LLM

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(empty)* | Key for `claude-*` models. Enables report synthesis |
| `OPENAI_API_KEY` | *(empty)* | Key for `gpt-*` / `o*` models. Enables report synthesis |
| `LLM_CHEAP_MODEL` | `claude-haiku-4-5` | Model id picks the vendor. Absent key → rules engine |
| `LLM_SMART_MODEL` | `claude-opus-5` | Model id picks the vendor. Absent key → rules engine |
| `LLM_CHEAP_MODEL` | `claude-haiku-4-5` | Strategy planning; runs often |
| `LLM_SMART_MODEL` | `claude-opus-5` | Report synthesis; qualified prospects only |
| `LLM_ENABLED` | `true` | Master switch |

### Crawling

| Variable | Default | Purpose |
|---|---|---|
| `HTTP_USER_AGENT` | identifies the bot | Change the contact URL to one you control |
| `CRAWL_MAX_PAGES_PER_SITE` | `12` | Page budget per company |
| `CRAWL_DELAY_SECONDS` | `1.0` | Delay between requests to the same host |
| `RESPECT_ROBOTS_TXT` | `true` | Leave on |
| `ENABLE_PLAYWRIGHT` | `false` | Render client-side sites |

### Guardrails

| Variable | Default | Purpose |
|---|---|---|
| `MAX_COMPANIES_PER_JOB` | `250` | Hard ceiling per research job |
| `DEFAULT_CAMPAIGN_BUDGET_USD` | `25` | Default campaign budget |

---

## Database

```bash
alembic upgrade head                            # apply
alembic downgrade -1                            # roll back one
alembic revision --autogenerate -m "add x"      # new migration after a model change
alembic current                                 # applied revision
```

The initial migration builds all 48 tables from the SQLAlchemy metadata, so the ORM and
a fresh install can never disagree. Later changes use ordinary autogenerated revisions.

Backup and restore:

```bash
docker compose exec postgres pg_dump -U prospectiq prospectiq > backup.sql
cat backup.sql | docker compose exec -T postgres psql -U prospectiq prospectiq
```

---

## Production deployment

### Before going live

- [ ] Replace `SECRET_KEY` and set `ENCRYPTION_KEY` explicitly
- [ ] `ENVIRONMENT=production`, `DEBUG=false`
- [ ] Restrict `CORS_ORIGINS` to your real frontend origin
- [ ] Terminate TLS at the load balancer; run uvicorn with `--proxy-headers`
- [ ] Use managed PostgreSQL and Redis with automated backups
- [ ] Set `HTTP_USER_AGENT` to a contact URL you control
- [ ] Review discovery connector terms for your jurisdiction and use
- [ ] Point structured logs at your aggregator (`ENVIRONMENT=production` emits JSON)
- [ ] Set per-organisation budgets in Administration → Cost

### AWS

| Component | Service |
|---|---|
| API + workers | ECS Fargate (separate services, same image, different commands) |
| Database | RDS PostgreSQL 16 — enable `pgvector` |
| Cache/broker | ElastiCache for Redis |
| Frontend | S3 + CloudFront (`npm run build` → `dist/`) |
| Secrets | Secrets Manager, injected as task environment |
| Images | ECR |

Run migrations as a one-off ECS task before rolling out a new task definition:

```bash
aws ecs run-task --cluster prospectiq --task-definition prospectiq-migrate \
  --overrides '{"containerOverrides":[{"name":"backend","command":["alembic","upgrade","head"]}]}'
```

### Azure

| Component | Service |
|---|---|
| API + workers | Container Apps (two apps, one image) |
| Database | Azure Database for PostgreSQL Flexible Server |
| Cache/broker | Azure Cache for Redis |
| Frontend | Static Web Apps |
| Secrets | Key Vault via managed identity |
| Images | Azure Container Registry |

Workers are queue-driven and stateless — scale them on queue depth. The API scales on
CPU/RPS. Keep exactly one `beat` replica.

### Health endpoints

| Endpoint | Use |
|---|---|
| `GET /health` | Liveness — process is up |
| `GET /health/ready` | Readiness — database and Redis reachable |
| `GET /system/status` | Capability report: which connectors and models are usable |

---

## Troubleshooting

**Research finds zero companies.** Check `GET /system/status`. If no connector is
available, enable OpenStreetMap or add a search key. Note that OpenStreetMap needs a
**city** in the campaign filters — it geocodes a place to search around.

**`password authentication failed` against a local database.** A native PostgreSQL is
occupying port 5432 ahead of the container. Publish the container on another port
(`POSTGRES_PORT=55432`) and update `DATABASE_URL`.

**Job stays queued.** No Celery worker is consuming the `research` queue. Start one, or
retry with `run_inline: true`. Jobs with no progress for 90 minutes are failed
automatically by the `reap_stuck_jobs` maintenance task.

**A company is `needs_verification` with "almost no text".** The site is
JavaScript-rendered. Enable Playwright. The platform deliberately does not call it fake.

**Reports read mechanically.** No key for the selected models (`ANTHROPIC_API_KEY` for
`claude-*`, `OPENAI_API_KEY` for `gpt-*`) — the rules engine is writing
them. Facts are identical either way; only the prose differs.
