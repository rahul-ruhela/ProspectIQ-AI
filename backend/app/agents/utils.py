"""Helpers shared by the AI employees."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.agents.base import AgentContext
from app.models.company import Company


def as_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


def load_company(ctx: AgentContext, payload: dict[str, Any]) -> Company | None:
    company_id = as_uuid(payload.get("company_id")) or ctx.company_id
    if company_id is None:
        return None
    return ctx.db.execute(select(Company).where(Company.id == company_id)).scalar_one_or_none()
