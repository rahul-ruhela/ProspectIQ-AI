"""Per-model daily request accounting, so free tiers are spent fully but never exceeded.

Free LLM tiers are metered per model per day, not per vendor. Two consequences shape
this module:

* Capacity multiplies across models. ``gemini-3.5-flash-lite`` running out says nothing
  about ``gemini-3.5-flash``, so the facade should move to the next model in the chain
  rather than give up on the whole run.
* Exhaustion must be remembered. Re-discovering a spent quota costs a wasted HTTP
  round trip on every subsequent call, and there can be thousands in one research job.

State lives in Redis when it is reachable, because Celery workers and the API run in
separate processes and must share one view of what is left. When Redis is absent the
ledger degrades to a per-process dictionary: less accurate across workers, but never a
reason for the platform to fail.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_KEY_PREFIX = "prospectiq:llm:quota"
# Kept well past the UTC day it describes so a late-running job still sees its own
# counters, while nothing accumulates indefinitely.
_TTL_SECONDS = 48 * 3600


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(UTC)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((tomorrow - now).total_seconds()))


class DailyQuotaLedger:
    """Tracks calls and exhaustion per model for the current UTC day."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._memory: dict[str, int] = {}
        self._exhausted: dict[str, str] = {}
        self._redis: Any = None
        self._redis_checked = False

    # --- storage ----------------------------------------------------------
    @property
    def redis(self) -> Any:
        """A live Redis handle, or None. Probed once; failure is not fatal."""
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
            logger.info("llm_quota_redis_unavailable", error=str(exc))
            self._redis = None
        return self._redis

    @staticmethod
    def _count_key(model: str) -> str:
        return f"{_KEY_PREFIX}:{_today()}:count:{model}"

    @staticmethod
    def _exhausted_key(model: str) -> str:
        return f"{_KEY_PREFIX}:{_today()}:exhausted:{model}"

    # --- reads ------------------------------------------------------------
    def used_today(self, model: str) -> int:
        client = self.redis
        if client is not None:
            try:
                return int(client.get(self._count_key(model)) or 0)
            except Exception:
                pass
        with self._lock:
            return self._memory.get(self._count_key(model), 0)

    def is_exhausted(self, model: str) -> bool:
        """True when this model already refused work today."""
        client = self.redis
        if client is not None:
            try:
                if client.get(self._exhausted_key(model)):
                    return True
            except Exception:
                pass
        with self._lock:
            if self._exhausted.get(model) == _today():
                return True
        cap = settings.LLM_DAILY_CAP_PER_MODEL
        return bool(cap > 0 and self.used_today(model) >= cap)

    def available(self, models: list[str]) -> list[str]:
        """The subset of ``models`` still worth trying today, in the given order."""
        return [m for m in models if not self.is_exhausted(m)]

    # --- writes -----------------------------------------------------------
    def record_call(self, model: str) -> None:
        key = self._count_key(model)
        client = self.redis
        if client is not None:
            try:
                pipe = client.pipeline()
                pipe.incr(key)
                pipe.expire(key, _TTL_SECONDS)
                pipe.execute()
                return
            except Exception:
                pass
        with self._lock:
            self._memory[key] = self._memory.get(key, 0) + 1

    def mark_exhausted(self, model: str, reason: str = "") -> None:
        """Stop routing to ``model`` for the rest of the UTC day."""
        logger.warning(
            "llm_model_exhausted", model=model, reason=reason[:200], used=self.used_today(model)
        )
        client = self.redis
        if client is not None:
            try:
                client.set(
                    self._exhausted_key(model), reason[:200] or "1",
                    ex=_seconds_until_utc_midnight(),
                )
                return
            except Exception:
                pass
        with self._lock:
            self._exhausted[model] = _today()

    def reset(self, models: list[str] | None = None) -> int:
        """Clear today's exhaustion flags, e.g. after billing or a key is fixed.

        Without this an operator who fixes their quota mid-morning would still see
        every model skipped until UTC midnight.
        """
        cleared = 0
        client = self.redis
        targets = models or []
        if client is not None:
            try:
                keys = (
                    [self._exhausted_key(m) for m in targets]
                    if targets
                    else list(client.scan_iter(f"{_KEY_PREFIX}:{_today()}:exhausted:*"))
                )
                for key in keys:
                    cleared += int(client.delete(key) or 0)
            except Exception as exc:
                logger.warning("llm_quota_reset_failed", error=str(exc))
        with self._lock:
            if targets:
                for model in targets:
                    cleared += 1 if self._exhausted.pop(model, None) else 0
            else:
                cleared += len(self._exhausted)
                self._exhausted.clear()
        logger.info("llm_quota_reset", models=targets or "all", cleared=cleared)
        return cleared

    # --- reporting --------------------------------------------------------
    def snapshot(self, models: list[str]) -> list[dict[str, Any]]:
        """Per-model usage for the status endpoint and the UI."""
        cap = settings.LLM_DAILY_CAP_PER_MODEL
        rows: list[dict[str, Any]] = []
        for model in models:
            used = self.used_today(model)
            rows.append(
                {
                    "model": model,
                    "used_today": used,
                    "daily_cap": cap or None,
                    "remaining": max(0, cap - used) if cap > 0 else None,
                    "exhausted": self.is_exhausted(model),
                }
            )
        return rows


_ledger: DailyQuotaLedger | None = None


def get_ledger() -> DailyQuotaLedger:
    global _ledger
    if _ledger is None:
        _ledger = DailyQuotaLedger()
    return _ledger
