"""Liveness, readiness and system-status endpoints."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.connectors.search import connector_statuses
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import DbSession
from app.llm.client import get_llm

router = APIRouter(tags=["System"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.APP_VERSION}


@router.get("/health/ready")
def ready(db: DbSession) -> dict:
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"

    try:
        import redis

        redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"

    healthy = all(v == "ok" for v in checks.values())
    return {"status": "ready" if healthy else "degraded", "checks": checks}


@router.get("/system/status")
def system_status() -> dict:
    """What the platform can actually do right now, given the current configuration."""
    llm = get_llm()
    connectors = connector_statuses()
    return {
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "llm": {
            "available": llm.available,
            "providers": llm.configured_providers,
            "free_tier_only": settings.LLM_FREE_TIER_ONLY,
            "cheap_model": settings.LLM_CHEAP_MODEL,
            "cheap_chain": llm.chain_for("cheap"),
            "cheap_available": bool(llm.usable_chain("cheap")),
            "cheap_reason": llm.unavailable_reason(settings.LLM_CHEAP_MODEL),
            "smart_model": settings.LLM_SMART_MODEL,
            "smart_chain": llm.chain_for("smart"),
            "smart_available": bool(llm.usable_chain("smart")),
            "smart_reason": llm.unavailable_reason(settings.LLM_SMART_MODEL),
            # Per-model daily usage, so the UI can show what free capacity is left.
            "quota": llm.quota_snapshot()["models"],
            "note": None
            if llm.available
            else "The selected models cannot be served. Set the key for their vendor "
            "(GEMINI_API_KEY for gemini-*, ANTHROPIC_API_KEY for claude-*, "
            "OPENAI_API_KEY for gpt-*), or clear LLM_FREE_TIER_ONLY to allow paid "
            "models. Reports fall back to the rules engine either way.",
        },
        "discovery_connectors": connectors,
        "discovery_available": any(c["available"] for c in connectors),
        "playwright_rendering": settings.ENABLE_PLAYWRIGHT,
        "respect_robots_txt": settings.RESPECT_ROBOTS_TXT,
    }
