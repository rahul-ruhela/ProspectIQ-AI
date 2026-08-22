# API reference

Base URL: `http://localhost:8000` · versioned routes under `/api/v1` ·
interactive Swagger at `/docs`, ReDoc at `/redoc`, schema at `/openapi.json`.

All responses carry an `X-Request-ID` header — quote it when reporting a problem.

---

## Authentication

Bearer JWT. Register or log in, then send `Authorization: Bearer <access_token>`.

```bash
# Create an organization; the first user becomes its admin
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@company.com","password":"a-long-password","full_name":"You","organization_name":"Your Co"}'

# Log in
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@company.com","password":"a-long-password"}'
```

Both return `{ user, tokens: { access_token, refresh_token, expires_in } }`.

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/auth/register` | — | Create organization + admin user |
| POST | `/auth/login` | — | Exchange credentials for tokens |
| POST | `/auth/refresh` | — | New access token from a refresh token |
| GET | `/auth/me` | any | Current user |
| POST | `/auth/change-password` | any | Change own password |

### Roles

`admin` > `researcher` > `sales_user` > `viewer`. A role satisfies any requirement at or
below it. `403` responses name the role required.

---

## Reference data

| Method | Path | Purpose |
|---|---|---|
| GET | `/reference/countries` | Supported countries (ISO2, continent, dial code) |
| GET | `/reference/industries` | Industry catalogue with AI-fit baselines |
| GET | `/reference/services` | Services you sell, with typical deal size |

---

## Campaigns

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/campaigns` | viewer | Paginated list |
| POST | `/campaigns` | researcher | Create |
| GET | `/campaigns/{id}` | viewer | Detail |
| PATCH | `/campaigns/{id}` | researcher | Update name, objective, filters, budget |
| DELETE | `/campaigns/{id}` | researcher | Archive (soft) |
| GET | `/campaigns/{id}/stats` | viewer | Companies, qualified, avg score, cost per prospect |
| POST | `/campaigns/{id}/start` | researcher | **Start research** |

```bash
curl -X POST http://localhost:8000/api/v1/campaigns \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
        "name": "HVAC automation — Texas",
        "objective": "Find small HVAC businesses in Texas that need AI automation.",
        "target_prospect_count": 25,
        "budget_usd": 10,
        "offered_services": ["ai_automation","ai_agents","lead_generation"],
        "filters": {
          "countries": ["US"],
          "industries": ["hvac"],
          "cities": ["Austin","Dallas"],
          "min_opportunity_score": 60,
          "require_website": true
        }
      }'
```

Naming **cities** lets the mapped-directory connector run, which returns structured
records (website, phone, address) rather than search snippets.

```bash
curl -X POST http://localhost:8000/api/v1/campaigns/$ID/start \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"max_companies": 25}'
```

Returns `202` with the research job. Add `"run_inline": true` to execute synchronously
without a Celery worker (development only).

---

## Research jobs

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/jobs` | viewer | List; filter by `campaign_id`, `job_status` |
| GET | `/jobs/{id}` | viewer | Live status, progress, plan, counters, cost |
| POST | `/jobs/{id}/cancel` | researcher | Stop cleanly between companies |
| POST | `/jobs/{id}/pause` | researcher | Pause |
| POST | `/jobs/{id}/resume` | researcher | Re-queue a paused or failed job |

Poll `/jobs/{id}` while `status` is `queued` or `running`; `progress_percent` and
`current_stage` update as the department works.

---

## Companies and prospects

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/companies` | viewer | Filter, sort, paginate |
| GET | `/companies/{id}` | viewer | Full detail with all provenance |
| GET | `/companies/{id}/report` | viewer | Sales-intelligence report |
| POST | `/companies/{id}/report/approve` | sales_user | **Human approval gate** |
| POST | `/companies/{id}/reject` | researcher | Reject with a reason |
| POST | `/companies/{id}/rescore` | researcher | Recompute after weight changes |
| GET | `/companies/export` | viewer | CSV including source, confidence, verified date |

List query parameters: `q`, `campaign_id`, `country_code`, `industry_slug`, `category`,
`min_score`, `max_score`, `has_contact`, `include_rejected`, `sort_by`, `sort_dir`,
`page`, `page_size`.

A company detail response includes `sources`, `website_record` (with `features` and
`pages`), `technologies`, `contacts` (with email/phone verification), `decision_makers`,
`signals`, `score` (with `breakdown`) and `research` (with `findings` and `evidence`).

Approving a report records the sign-off and moves the prospect to `ready_contact`. **It
does not send anything** — the platform has no outbound channel.

---

## AI employees

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/agents` | viewer | Roster with run counts and average confidence |
| GET | `/agents/status` | viewer | Live department snapshot |
| GET | `/agents/{key}` | viewer | Detail including input/output JSON schema |
| POST | `/agents/{key}/toggle` | admin | Enable or disable an employee |
| GET | `/agents/tasks` | viewer | Task queue; filter by job, company, agent, status |
| GET | `/agents/tasks/{id}/executions` | viewer | Per-attempt timing, tokens, cost |
| GET | `/agents/logs` | viewer | Execution log; filter by job, agent, level |
| GET | `/agents/messages` | viewer | Inter-agent messages on the orchestrator bus |

---

## CRM

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/crm/pipeline` | viewer | Board grouped by stage |
| POST | `/crm/{company_id}/stage` | sales_user | Move stage; logs an activity |
| POST | `/crm/{company_id}/contact-status` | sales_user | Record outreach; increments attempts |
| POST | `/crm/{company_id}/assign` | sales_user | Assign an owner |
| GET | `/crm/{company_id}/activities` | viewer | Timeline |
| POST | `/crm/{company_id}/activities` | sales_user | Add a note, call or meeting |
| GET | `/crm/follow-ups` | viewer | Due within `days_ahead` |
| POST | `/crm/feedback` | sales_user | Correct a score or report |
| GET | `/crm/stats` | viewer | Counts by stage and contact status |

Stages: `discovered → researching → qualified → ready_contact → contacted →
reply_received → meeting → proposal → negotiation → customer`, plus `lost`.

Contact statuses: `not_contacted`, `called`, `contacted`, `follow_up_required`,
`meeting_scheduled`, `not_interested`, `converted`. Setting one stamps
`last_contact_at` and increments `contact_attempts`, so nobody is called twice.

---

## Analytics

| Method | Path | Purpose |
|---|---|---|
| GET | `/analytics/dashboard` | Headline metrics |
| GET | `/analytics/overview?days=30` | Trends, distributions, funnel, cost, agent performance |

---

## Administration (admin only)

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/providers` · `/admin/models` | AI providers and models |
| PATCH | `/admin/models/{model_id}` | Change tier, pricing, enablement |
| GET/POST | `/admin/api-keys` | Stored encrypted; only a masked hint is returned |
| DELETE | `/admin/api-keys/{id}` | Remove a key |
| GET | `/admin/connectors` · `/admin/connectors/health` | Sources and live availability |
| PATCH | `/admin/connectors/{slug}` | Enable, rate-limit, cost |
| GET | `/admin/scoring-rules` | Current weights |
| PATCH | `/admin/scoring-rules/{component}` | Change a weight — **rejected unless active weights still total 100** |
| GET | `/admin/costs?days=30` | Spend by model and by agent, cost per prospect |
| GET/POST | `/users` · PATCH `/users/{id}` | User and role management |

---

## Conventions

**Pagination**

```json
{ "items": [], "total": 0, "page": 1, "page_size": 25, "pages": 1 }
```

**Errors**

```json
{ "detail": "Campaign not found" }
```

Validation errors return `422` with FastAPI's field-level array.

| Status | Meaning |
|---|---|
| 400 | Invalid request (e.g. starting research with no country selected) |
| 401 | Missing, invalid or expired token |
| 403 | Authenticated but the role is insufficient |
| 404 | Not found, or outside your organization |
| 409 | Conflict (duplicate email, job already running) |
| 422 | Schema validation failed |

**Provenance.** Every outward-facing fact includes `source`, `source_url`, `confidence`
(0–1), `verification_status` and `last_verified_at`. Inferences also carry `certainty` —
`observed`, `likely`, `possible` or `unknown`. A field that reads `"Unknown"` is a
deliberate answer, not a missing value.
