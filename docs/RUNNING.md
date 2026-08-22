# How to start ProspectIQ

There are three ways to run this. Pick one — you do not need all three.

---

## 1. The one-button way (recommended for development)

```bash
cd frontend
npm install     # first time only
npm run dev
```

Open <http://localhost:5173>.

If the backend is not running, the app shows a start screen instead of a broken
login page:

- It checks whether Docker Desktop is running.
- It lists the six backend services and their state.
- **Click "Start backend".** It runs `docker compose up -d` for you and streams the
  Docker output into the page.
- When the API answers on port 8000, the gate disappears and the real app loads.

Nothing else to open, no second terminal. If you prefer to run the backend
yourself, click "Skip — I run the backend myself".

### How this works

`npm run dev` starts a Node process (the Vite dev server), and a browser tab cannot
run Docker but that Node process can. [`frontend/devstack.plugin.ts`](../frontend/devstack.plugin.ts)
adds three routes to the dev server:

| Route | Does |
|---|---|
| `GET /__devstack/status` | Docker version, per-service state, whether the API answers |
| `POST /__devstack/start` | `docker compose up -d postgres redis backend worker beat flower` |
| `POST /__devstack/stop` | `docker compose stop` for the same services |

Two safety properties, both deliberate:

- The plugin is `apply: 'serve'`, so it exists in `npm run dev` **only**. It is not
  in a production build — verified by grepping the built bundle for `__devstack`.
- Only loopback callers are accepted. `server.host` is `true`, which publishes Vite
  to your LAN, and without that check anyone on your network could start and stop
  your containers.

The button deliberately does **not** start the `frontend` container — that would be
a second copy of the same app competing for a port.

---

## 2. Everything in Docker

```bash
docker compose up -d
```

Serves the production-style static build. Use this to check what deploys, not for
day-to-day work — there is no hot reload.

---

## 3. Backend by hand

```bash
cd backend
python -m venv venv
venv/Scripts/activate          # Windows;  source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Postgres and Redis still need to be running:
`docker compose up -d postgres redis`.

---

## Ports

| Port | Service | Notes |
|---|---|---|
| **5173** | Vite dev server | `npm run dev` — the one you want |
| 5174 | `frontend` container | Production-style static build |
| 8000 | Backend API | `/health`, `/api/v1/...`, docs at `/docs` |
| 5555 | Flower | Celery queue inspector |
| 55432 | Postgres | Non-standard on the host to avoid clashing with a local install |
| 6379 | Redis | Broker, result backend, and the LLM quota ledger |

> **Note:** the `frontend` container used to publish 5173, which collided with
> `npm run dev` and meant the browser silently loaded the stale container build
> instead of your live code. It now publishes 5174, so both can run at once.

---

## Health checks

```bash
curl http://localhost:8000/health          # liveness
curl http://localhost:8000/health/ready    # database + redis
curl http://localhost:8000/api/v1/system/status   # what the platform can actually do
```

`system/status` is the one worth reading. It reports which discovery connectors are
usable, which LLM models are configured, and how much free quota is left today.

---

## Watching a research job

Start a campaign, then click into the job. **The department floor** shows all 15
agents as a live grid: agents pulse blue while working, turn green as they finish,
and carry a count of how many companies each has handled. It is grouped by pipeline
phase, so the per-company agents that run concurrently light up together.

The view is built entirely from `AgentTask` rows the page already polls — it never
simulates activity that is not happening.

---

## Troubleshooting

**The start screen says Docker is not running.** Start Docker Desktop and wait for
the whale icon to settle. The panel picks it up within a few seconds on its own.

**Port 5173 already in use.** A `frontend` container from an older checkout is
probably still bound to it: `docker compose stop frontend`, then
`docker compose up -d frontend` to bring it back on 5174.

**The app loads but every request 401s.** Your seeded admin login is in
`backend/.env` as `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`.

**Reports have no AI narrative.** Expected when the LLM has no quota — see
[COSTS_AND_QUOTAS.md](COSTS_AND_QUOTAS.md). Scoring, verification and signals are
deterministic and keep working regardless.

**Nothing is discovered.** Check
`curl http://localhost:8000/api/v1/system/status | grep -i connector`. At least one
discovery connector must be available. OpenStreetMap and DuckDuckGo need no key.
