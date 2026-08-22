# What a research job actually costs

Short answer: **with the current configuration, nothing.** But the number shown on a
job is real accounting, not decoration, so it is worth knowing what it counts.

---

## 1. Where the `cost_usd` on a job comes from

```
job.cost_usd = LLM token cost + connector call cost
```

### LLM cost

The platform makes far fewer model calls than people assume. There are exactly
**two** LLM call sites in the whole codebase:

| Call site | When | Tier | Frequency |
|---|---|---|---|
| `orchestrator.py` — campaign brief interpretation | Once per job | cheap | **1 per job** |
| `report.py` — narrative sales report | Per qualified company | smart | **1 per company scoring ≥ 60** |

So a 200-company job that qualifies 30 prospects makes **31 LLM calls**, not 200 and
not thousands. Everything else — scoring, verification, tech detection, buying
signals, opportunity rules — is deterministic Python and costs nothing.

There is already a spend gate in `_worth_llm_spend()`: the expensive model is only
used on companies that already scored ≥ 60. Low-quality prospects never reach it.

**`estimate_cost()` returns `0.0` for free-tier models.** Reporting list prices for
calls that were never billed would eat campaign budgets that were never spent. Paid
models are always priced truthfully — that figure is what enforces the spend ceiling
in section 3.

### Connector cost

| Connector | Per call | Real money? |
|---|---|---|
| OpenStreetMap | $0.000 | No — free and unmetered |
| DuckDuckGo | $0.000 | No — free, rate limited |
| SearXNG | $0.000 | No — if you self-host |
| Serper | $0.001 | Only after your free credits run out |
| Google CSE | $0.005 | Only after 100 queries/day |

These are **estimates for budgeting**, not invoices. Nothing in this platform can
charge your card — the numbers exist so `campaign.budget_usd` can stop a runaway job
before it becomes expensive.

### The budget guard

The orchestrator checks before every company:

```python
if campaign.budget_usd and (campaign.spent_usd + ctx.usage.cost_usd) > campaign.budget_usd:
    # stop research
```

Set `budget_usd` on a campaign and the job stops itself rather than overrunning.

---

## 2. Using free tiers across providers

You asked to rotate free tiers across Gemini, OpenAI and Anthropic. One correction
worth making plainly, because it changes the design:

> **OpenAI and Anthropic have no free tier.** Both bill from the first token. There
> is no daily free allowance to rotate onto. Only Gemini offers a genuine no-card
> free tier.

So rotating *across vendors* is not possible. What **is** possible, and is now
implemented, is rotating across **models** — because free quotas are metered per
model per day, not per vendor. Three flash models is roughly three times the daily
free capacity of one.

### Model chains

`backend/app/core/config.py`:

```
LLM_CHEAP_MODEL_CHAIN=gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-flash-lite-latest
LLM_SMART_MODEL_CHAIN=gemini-3.5-flash,gemini-3.7-flash,gemini-flash-latest
```

Each tier walks its chain left to right. When a model returns `429`, the facade:

1. Marks that model exhausted for the rest of the **UTC day**.
2. Moves to the next model in the chain and retries the same work.
3. Falls back to the deterministic rules engine only when the whole chain is spent.

Only quota exhaustion advances the chain. An auth or network error is returned
immediately — it would fail identically on every model, so retrying would just
multiply one failure by the chain length.

### The quota ledger

`backend/app/llm/quota.py` tracks calls and exhaustion per model per UTC day, in
**Redis** so the API process and the Celery workers share one view. Without shared
state each worker would rediscover a spent quota independently, wasting an HTTP
round trip per call — and a large job makes thousands.

Check what is left:

```bash
curl http://localhost:8000/api/v1/system/status | python -m json.tool
```

Look under `llm.quota` for `used_today` and `exhausted` per model.

After fixing billing or swapping a key, clear the flags without waiting for
midnight:

```bash
cd backend
venv/Scripts/python.exe -c "from app.llm.quota import get_ledger; print(get_ledger().reset())"
```

### Free always comes first

Every chain lists free models first and exhausts them before a paid model is even
considered. Paid entries are appended only when the UI spend policy allows it and
both ceilings still have room — see section 3.

---

## 3. Paid models, capped from the UI

Paid models are now available as a **fallback**, never a first choice, and only
inside a ceiling you set yourself.

**Admin → AI models → "Paid AI spend"**

| Control | What it does |
|---|---|
| Allow paid models | Master toggle. Off by default |
| Daily limit | Presets $0.50 / $1 / $5 / $20, or type any figure. Resets at UTC midnight |
| Monthly limit | Presets $5 / $20 / $50 / $100, or custom. Calendar month, UTC |
| Warn at | 50 / 75 / 80 / 90% — the meter turns amber past this point |

Both meters show live spend against the limit, with the remaining balance underneath.
The panel also prints the exact model order a change unlocks, so you can see what
you just enabled:

```
gemini-3.5-flash-lite  gemini-3.1-flash-lite  gemini-flash-lite-latest  then  gpt-4o-mini
```

### How the ceiling is enforced

`backend/app/llm/spend.py` keeps two counters — spend today and spend this month —
and `chain_for()` appends paid models **only** while both still have room. The
instant a limit is crossed, paid models vanish from the chain and the run falls back
to the rules engine.

Three properties worth knowing:

* **Counters live in Redis**, so the API and every Celery worker enforce one shared
  budget. Two workers each holding a private half-spent counter would together
  overshoot the limit.
* **Redis is a cache, not the record.** `ai_usage` rows are the truth, so a flushed
  cache reseeds from the database rather than resetting spend to zero and handing
  out a second budget.
* **The check is pre-flight.** A call's true cost is unknown until it returns, so
  the guard blocks the *next* call once the line is crossed. Overshoot is bounded by
  one call — fractions of a cent at these model prices.

### Master kill switch

`LLM_FREE_TIER_ONLY=true` in `.env` overrides the UI entirely: no paid call, ever,
whatever the policy says. Use it for CI or a shared demo. It is now `false`, so the
UI policy governs.

### Measured cost

A real call through the fallback chain, after the free Gemini models were exhausted:

```
model  : gpt-4o-mini
tokens : 19 in / 2 out
cost   : $0.000004
```

You were right that OpenAI is cheap. At that rate a $0.50 daily cap is roughly
125,000 short calls — and the platform only makes one LLM call per job plus one per
qualified prospect, so the cap is very hard to reach in normal use.

---

## 4. Spending fewer tokens

Already in place:

| Measure | Effect |
|---|---|
| `_worth_llm_spend()` gate | The smart model only runs on companies scoring ≥ 60 |
| `LLM_MAX_PROMPT_CHARS=12000` | Prompts truncated before sending. Crawled page text is the only unbounded input and its tail is boilerplate |
| Report `max_tokens` 4096 → **1536** | The report schema is a handful of short fields; the rest was unused headroom, and on a metered tier headroom is the cost |
| `thinkingConfig: {thinkingBudget: 0}` on flash models | No thinking tokens billed against your per-minute budget |
| Cheap tier by default | Only report synthesis uses the smart tier |
| Exhaustion memoised in Redis | A spent model costs zero further round trips that day |

---

## 5. Current status of your keys

Measured against live endpoints on 2026-08-22:

| Key | Status |
|---|---|
| Serper | ✅ Working — returns real results |
| Google CSE key | ✅ Valid |
| Google CSE cx (`410c77a9df4d44063`) | ⚠️ Correct ID, but **Custom Search JSON API is not enabled** on the project |
| Gemini | ⚠️ Authenticates, but **prepaid balance is empty** on project `89788847888` |

### To fix Google CSE

The `cx` was stored as a full URL; only the ID belongs in the variable, and that is
now corrected. The remaining error is:

```
403 — This project does not have the access to Custom Search JSON API.
```

Enable it: <https://console.cloud.google.com/apis/library/customsearch.googleapis.com>
→ select project `89788847888` → **Enable**.

### To fix Gemini

Every model returns `429 — "Your prepayment credits are depleted"`. This is not a
daily ceiling that resets; the project is on prepaid billing with a zero balance.
Issue a key from an AI Studio project that still has free-tier access, or load
credits — which is the spend you asked to avoid.

Until then discovery runs on **OpenStreetMap + Serper + DuckDuckGo**, and every
deterministic feature works normally. The only loss is narrative report prose.
