"""Spend policy and live budget enforcement for paid LLM calls.

The platform can use paid models, but only inside a ceiling the operator sets from
the UI. Two counters back that promise - spend today and spend this month - and a
paid model is only ever offered when both still have room.

Design notes:

* Counters live in Redis so the API and every Celery worker enforce one shared
  budget. Two workers each holding a private half-spent counter would together
  overshoot the limit.
* Redis is a cache, not the record. ``ai_usage`` rows are the truth, so a cold or
  flushed cache reseeds itself from the database rather than resetting spend to zero
  and handing out a second budget.
* The check is deliberately *pre-flight and approximate*. A call's true cost is
  unknown until it returns, so the guard blocks the next call once the line is
  crossed. Overshoot is bounded by one call, which for the models used here is
  fractions of a cent.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_PREFIX = "prospectiq:llm:spend"
_POLICY_KEY = f"{_PREFIX}:policy"
_POLICY_TTL = 60  # Short: a limit change from the UI must take effect promptly.


def _day() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _month() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(UTC)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((tomorrow - now).total_seconds()))


@dataclass(slots=True)
class SpendPolicy:
    """What the operator has allowed. Mirrors the ``llm_spend_policy`` row."""

    allow_paid: bool = False
    daily_limit_usd: float = 0.50
    monthly_limit_usd: float = 20.0
    alert_threshold_pct: float = 80.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SpendPolicy":
        return cls(
            allow_paid=bool(raw.get("allow_paid", False)),
            daily_limit_usd=float(raw.get("daily_limit_usd", 0.50) or 0.0),
            monthly_limit_usd=float(raw.get("monthly_limit_usd", 20.0) or 0.0),
            alert_threshold_pct=float(raw.get("alert_threshold_pct", 80.0) or 0.0),
        )


class SpendLedger:
    """Tracks paid spend against the operator's daily and monthly ceilings."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._memory: dict[str, float] = {}
        self._policy: SpendPolicy | None = None
        self._policy_loaded_at: float = 0.0
        self._redis: Any = None
        self._redis_checked = False

    # --- storage ----------------------------------------------------------
    @property
    def redis(self) -> Any:
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        try:
            import redis

            client = redis.Redis.from_url(
                settings.REDIS_URL, socket_connect_timeout=2, decode_responses=True
            )
            client.ping()
            self._redis = client
        except Exception as exc:
            logger.info("llm_spend_redis_unavailable", error=str(exc))
            self._redis = None
        return self._redis

    # --- policy -----------------------------------------------------------
    def policy(self) -> SpendPolicy:
        """The active policy, cached briefly so hot paths do not hit the database."""
        import json
        import time

        now = time.monotonic()
        if self._policy is not None and (now - self._policy_loaded_at) < _POLICY_TTL:
            return self._policy

        client = self.redis
        if client is not None:
            try:
                raw = client.get(_POLICY_KEY)
                if raw:
                    self._policy = SpendPolicy.from_dict(json.loads(raw))
                    self._policy_loaded_at = now
                    return self._policy
            except Exception:
                pass

        policy = self._load_policy_from_db()
        self._policy = policy
        self._policy_loaded_at = now
        self.cache_policy(policy)
        return policy

    def _load_policy_from_db(self) -> SpendPolicy:
        try:
            from app.core.database import SessionLocal
            from app.models.admin import SpendPolicyRow
            from sqlalchemy import select

            with SessionLocal() as db:
                row = db.execute(select(SpendPolicyRow).limit(1)).scalar_one_or_none()
                if row is None:
                    return SpendPolicy()
                return SpendPolicy(
                    allow_paid=row.allow_paid,
                    daily_limit_usd=row.daily_limit_usd,
                    monthly_limit_usd=row.monthly_limit_usd,
                    alert_threshold_pct=row.alert_threshold_pct,
                )
        except Exception as exc:
            # A missing table (pre-migration) or an unreachable database must never
            # be an implicit licence to spend, so the safe default is returned.
            logger.info("llm_spend_policy_db_unavailable", error=str(exc))
            return SpendPolicy()

    def cache_policy(self, policy: SpendPolicy) -> None:
        """Publish a policy change so every process picks it up within the TTL."""
        import json
        import time

        self._policy = policy
        self._policy_loaded_at = time.monotonic()
        client = self.redis
        if client is not None:
            try:
                client.set(_POLICY_KEY, json.dumps(policy.to_dict()), ex=3600)
            except Exception:
                pass

    def invalidate_policy(self) -> None:
        self._policy = None
        self._policy_loaded_at = 0.0

    # --- counters ---------------------------------------------------------
    def _key(self, period: str) -> str:
        return f"{_PREFIX}:{period}"

    def _read(self, period: str) -> float:
        key = self._key(period)
        client = self.redis
        if client is not None:
            try:
                raw = client.get(key)
                if raw is not None:
                    return float(raw)
                # Cold cache: reseed from the durable record so a Redis restart
                # cannot silently grant a fresh budget.
                seeded = self._sum_usage_from_db(period)
                client.set(key, seeded, ex=_TTL_FOR[period]())
                return seeded
            except Exception:
                pass
        with self._lock:
            return self._memory.get(key, 0.0)

    def _sum_usage_from_db(self, period: str) -> float:
        try:
            from app.core.database import SessionLocal
            from app.models.admin import AIUsage
            from sqlalchemy import func, select

            if period.count("-") == 2:  # YYYY-MM-DD
                start = datetime.strptime(period, "%Y-%m-%d").replace(tzinfo=UTC)
                end = start + timedelta(days=1)
            else:  # YYYY-MM
                start = datetime.strptime(period + "-01", "%Y-%m-%d").replace(tzinfo=UTC)
                end = (start + timedelta(days=32)).replace(day=1)
            with SessionLocal() as db:
                total = db.execute(
                    select(func.sum(AIUsage.cost_usd)).where(
                        AIUsage.created_at >= start, AIUsage.created_at < end
                    )
                ).scalar_one()
            return float(total or 0.0)
        except Exception as exc:
            logger.info("llm_spend_reseed_failed", period=period, error=str(exc))
            return 0.0

    def spent_today(self) -> float:
        return self._read(_day())

    def spent_this_month(self) -> float:
        return self._read(_month())

    def record(self, cost_usd: float) -> None:
        """Add a completed call's cost to both counters."""
        if cost_usd <= 0:
            return
        client = self.redis
        for period in (_day(), _month()):
            key = self._key(period)
            if client is not None:
                try:
                    pipe = client.pipeline()
                    pipe.incrbyfloat(key, cost_usd)
                    pipe.expire(key, _TTL_FOR[period]())
                    pipe.execute()
                    continue
                except Exception:
                    pass
            with self._lock:
                self._memory[key] = self._memory.get(key, 0.0) + cost_usd

    # --- enforcement ------------------------------------------------------
    def paid_allowed(self) -> bool:
        """True when paid models may be used right now."""
        policy = self.policy()
        if not policy.allow_paid:
            return False
        if policy.daily_limit_usd > 0 and self.spent_today() >= policy.daily_limit_usd:
            return False
        if policy.monthly_limit_usd > 0 and self.spent_this_month() >= policy.monthly_limit_usd:
            return False
        return True

    def block_reason(self) -> str | None:
        """Why paid models are unavailable, or None when they are available."""
        policy = self.policy()
        if not policy.allow_paid:
            return "Paid models are switched off."
        if policy.daily_limit_usd > 0 and self.spent_today() >= policy.daily_limit_usd:
            return (
                f"Daily limit reached: ${self.spent_today():.4f} of "
                f"${policy.daily_limit_usd:.2f}. Resets at UTC midnight."
            )
        if policy.monthly_limit_usd > 0 and self.spent_this_month() >= policy.monthly_limit_usd:
            return (
                f"Monthly limit reached: ${self.spent_this_month():.4f} of "
                f"${policy.monthly_limit_usd:.2f}."
            )
        return None

    def status(self) -> dict[str, Any]:
        """Everything the UI needs to render the budget meter."""
        policy = self.policy()
        today = self.spent_today()
        month = self.spent_this_month()

        def pct(spent: float, limit: float) -> float:
            return round(min(100.0, (spent / limit) * 100), 2) if limit > 0 else 0.0

        daily_pct = pct(today, policy.daily_limit_usd)
        monthly_pct = pct(month, policy.monthly_limit_usd)
        return {
            "policy": policy.to_dict(),
            "spent_today_usd": round(today, 6),
            "spent_month_usd": round(month, 6),
            "daily_used_pct": daily_pct,
            "monthly_used_pct": monthly_pct,
            "daily_remaining_usd": round(max(0.0, policy.daily_limit_usd - today), 6),
            "monthly_remaining_usd": round(max(0.0, policy.monthly_limit_usd - month), 6),
            "paid_available": self.paid_allowed(),
            "blocked_reason": self.block_reason(),
            "alerting": bool(
                policy.allow_paid
                and policy.alert_threshold_pct > 0
                and max(daily_pct, monthly_pct) >= policy.alert_threshold_pct
            ),
        }

    def reset(self) -> None:
        """Clear the live counters. Used by tests and by an operator starting over."""
        client = self.redis
        if client is not None:
            try:
                client.delete(self._key(_day()), self._key(_month()))
            except Exception:
                pass
        with self._lock:
            self._memory.clear()


class _TTLMap(dict):
    """TTL per counter key: daily counters die at midnight, monthly ones outlive the month.

    A plain dict would need repopulating every time the date rolls over mid-process,
    so the TTL is derived from the period's shape instead.
    """

    def __missing__(self, period: str) -> Any:
        is_daily = period.count("-") == 2  # YYYY-MM-DD vs YYYY-MM
        return _seconds_until_utc_midnight if is_daily else (lambda: 40 * 24 * 3600)


_TTL_FOR = _TTLMap()

_ledger: SpendLedger | None = None


def get_spend_ledger() -> SpendLedger:
    global _ledger
    if _ledger is None:
        _ledger = SpendLedger()
    return _ledger
