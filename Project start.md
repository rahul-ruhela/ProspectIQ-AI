# Project start

Simple steps to run ProspectIQ AI, plus what every API key is for and how to
inspect the database in pgAdmin.

---

## 1. Start the app — one command

Open PowerShell in the repo root (`c:\work\ai-tools\ProspectIQ-AI`) and run:

```powershell
docker compose up -d --build
```

That is the whole app. It builds the images and starts seven containers:
Postgres, Redis, the API, the Celery worker, the Celery beat scheduler, Flower
and the frontend. The API container runs the database migrations and the seeder
by itself on boot — you never run those by hand.

**You do not need Python, pip or a venv installed.** The backend image ships its
own Python 3.12 and installs the dependencies inside itself when it builds. Your
Windows Python is never touched.

### Step by step

```powershell
# 1. go to the repo root
cd c:\work\ai-tools\ProspectIQ-AI

# 2. build and start everything
docker compose up -d --build

# 3. watch it come up (Ctrl+C stops watching, not the app)
docker compose logs -f backend

# 4. confirm all seven say "healthy"
docker compose ps

# 5. check keys and connectors are live
curl http://localhost:8000/system/status
```

Then open http://localhost:5173 and log in with the `SEED_ADMIN_EMAIL` /
`SEED_ADMIN_PASSWORD` from `backend/.env`.

| What | URL |
|---|---|
| App (frontend) | http://localhost:5173 |
| API docs | http://localhost:8000/docs |
| Capability status | http://localhost:8000/system/status |
| Flower (task queue) | http://localhost:5555 |

### Stopping and restarting

```powershell
docker compose stop        # pause the app, containers kept
docker compose start       # resume after a stop
docker compose down        # remove the containers, DATABASE IS KEPT
docker compose down -v     # remove containers AND DELETE the database
```

`stop` and `down` both leave your data alone. Only `-v` wipes it.

### After you change something

| You changed | Run this |
|---|---|
| `backend/.env` (a key, a model) | `docker compose restart backend worker` |
| Any code | `docker compose up -d --build` |
| Nothing, just want it running | `docker compose up -d` |

Editing `.env` and saving is not enough — environment variables are read once
when a container starts. Editing code needs `--build`, because a plain restart
reuses the image that was already built.

### Everyday commands

```powershell
docker compose ps                      # what is running
docker compose logs -f backend worker  # follow logs
docker compose logs --tail=50 backend  # last 50 lines
docker exec -it prospectiq-backend sh  # shell inside the API container
```

---

## 2. Running without Docker — you almost certainly do not need this

Skip this section unless you are debugging the backend in an IDE. It is the only
reason a venv exists in this project.

A venv is a private folder of Python packages so this project's dependencies do
not collide with anything else on your machine. Docker gives you the same
isolation and more, which is why the venv is redundant when you use Compose.

Note your Windows Python is 3.14 while the project is built and tested on 3.12,
so this path can hit differences Docker does not.

```powershell
# infrastructure still comes from Docker
docker compose up -d postgres redis

# backend (terminal 1)
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head              # Docker does this for you; here you must
python -m app.seed.seeder
uvicorn app.main:app --reload --port 8000

# worker (terminal 2, venv activated)
cd backend
venv\Scripts\activate
celery -A app.workers.celery_app.celery_app worker --loglevel=info -Q research,enrichment,default

# frontend (terminal 3)
cd frontend
npm install
npm run dev
```

Tests: `cd backend; venv\Scripts\python.exe -m pytest -q`

---

## 3. What each API key is for

Nothing here is mandatory. The platform is built to degrade rather than fail:
with no keys at all it still discovers companies through two keyless sources and
writes reports with the deterministic rules engine.

### AI / LLM keys

| Variable | What it does |
|---|---|
| `ANTHROPIC_API_KEY` | Serves the `claude-*` models. https://console.anthropic.com/settings/keys |
| `OPENAI_API_KEY` | Serves the `gpt-*` / `o*` models. https://platform.openai.com/api-keys |

The vendor is chosen by the **model id**, not by a separate provider setting:

```env
LLM_CHEAP_MODEL=claude-haiku-4-5    # -> needs ANTHROPIC_API_KEY
LLM_SMART_MODEL=claude-opus-5       # -> needs ANTHROPIC_API_KEY
```

Point either tier at `gpt-4o-mini` / `gpt-4o` to use OpenAI instead. Mixing
vendors across tiers is supported. Without a key for the selected models,
reports fall back to the rules engine — no data is ever invented either way.

### Discovery connectors

These find the companies to research. **At least one must work**, and two of
them already do with no signup. They are tried in preference order — best
quality first, free fallback last.

| Variable | Connector | Cost | How to get it |
|---|---|---|---|
| `SERPER_API_KEY` | Google results via serper.dev | ~$0.001/search, 2,500 free credits | Sign up at https://serper.dev → the key is on your dashboard. **Best quality — this is the one worth paying for.** |
| `GOOGLE_CSE_KEY` + `GOOGLE_CSE_CX` | Google Programmable Search | 100 free queries/day, then ~$5 per 1,000 | Both are needed, from two different places — see below |
| `SEARXNG_URL` | Your own SearXNG instance | Free, unmetered | Not a key — the URL of a SearXNG server you host, e.g. `http://localhost:8080`. See https://docs.searxng.org |
| `ENABLE_DUCKDUCKGO=true` | DuckDuckGo HTML scraping | Free | **No key needed.** Already on. Rate-limited and best-effort |
| `ENABLE_OPENSTREETMAP=true` | OpenStreetMap Overpass | Free | **No key needed.** Already on. Returns structured records — name, website, phone, address — with a citable source URL |

**Getting the two Google values** (they are not the same thing):

1. `GOOGLE_CSE_KEY` — an API key from https://console.cloud.google.com/apis/credentials.
   Create a project, then enable the *Custom Search API* for it, then create an
   API key.
2. `GOOGLE_CSE_CX` — the *search engine ID* from
   https://programmablesearchengine.google.com/controlpanel/all. Create a search
   engine, set it to **search the entire web**, and copy the ID.

Both must be set or the connector stays off.

**Recommendation:** start with the two keyless sources. OpenStreetMap is
genuinely good for local trades and bricks-and-mortar businesses. Add Serper
when you need broader reach and better result quality.

### Checking what is actually live

```powershell
curl http://localhost:8000/system/status
```

Every connector reports `available` plus a `reason` explaining exactly what is
missing, so you never have to guess which key failed.

---

## 4. Viewing the database in pgAdmin

Postgres is published on host port **55432** (not the default 5432 — that avoids
clashing with any other Postgres on your machine). The port comes from
`POSTGRES_PORT` in the repo-root `.env`.

In pgAdmin: right-click **Servers → Register → Server…**

**General tab**

| Field | Value |
|---|---|
| Name | `ProspectIQ (local)` |

**Connection tab**

| Field | Value |
|---|---|
| Host name/address | `localhost` |
| Port | `55432` |
| Maintenance database | `prospectiq` |
| Username | `prospectiq` |
| Password | `prospectiq` |
| Save password | ✔ |

Click **Save**. The tables are under
`ProspectIQ (local) → Databases → prospectiq → Schemas → public → Tables`.

Credentials come from `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` in
the repo-root `.env` — change them there if you change them at all.

### Don't have pgAdmin installed?

Add it to the stack as a container. Append to `docker-compose.yml` under
`services:`:

```yaml
  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: prospectiq-pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@prospectiq.local
      PGADMIN_DEFAULT_PASSWORD: admin
      PGADMIN_CONFIG_SERVER_MODE: "False"
    ports:
      - "5050:80"
    depends_on:
      - postgres
    restart: unless-stopped
```

Then `docker compose up -d pgadmin` and open http://localhost:5050.

> From **inside** that container the host is `postgres` and the port is `5432` —
> containers talk to each other on the compose network, not through the
> published host port. Use `localhost:55432` only from a pgAdmin installed on
> Windows.

### Quick look without pgAdmin

```powershell
docker exec -it prospectiq-postgres psql -U prospectiq -d prospectiq

# then, at the psql prompt:
\dt                          -- list tables
\d companies                 -- describe a table
SELECT count(*) FROM companies;
\q                           -- quit
```

---

## 5. When something is wrong

| Symptom | Cause |
|---|---|
| Reports read mechanically | No key for the selected models. Check `/system/status` |
| "No discovery connectors available" | All of them are off — `ENABLE_OPENSTREETMAP` and `ENABLE_DUCKDUCKGO` should be `true` |
| Key changes have no effect | The container did not restart. `docker compose restart backend worker` |
| Code changes have no effect | The image was not rebuilt. `docker compose up -d --build` |
| pgAdmin cannot connect | Wrong port. It is `55432`, not `5432` |
| Jobs stay queued forever | The worker is down. `docker compose logs worker` |

Fuller reference: [docs/INSTALL.md](docs/INSTALL.md).
