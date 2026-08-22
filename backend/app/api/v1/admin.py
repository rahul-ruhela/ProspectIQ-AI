"""Administration: AI providers, models, API keys, connectors, scoring, catalogues, costs."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.connectors.search import connector_statuses
from app.core.deps import CurrentUser, DbSession, OrgId, RequireAdmin, audit
from app.core.security import encrypt_secret, mask_secret
from app.llm.client import get_llm
from app.llm.spend import SpendPolicy, get_spend_ledger
from app.models.admin import (
    AIModel,
    AIProvider,
    AIUsage,
    APIKey,
    Connector,
    ScoringRule,
    ServiceCatalogItem,
    SpendPolicyRow,
)
from app.models.company import Company
from app.models.geo import Country, Industry
from app.schemas.admin import (
    AIModelOut,
    AIModelUpdate,
    AIProviderOut,
    APIKeyCreate,
    APIKeyOut,
    ConnectorHealth,
    ConnectorOut,
    ConnectorUpdate,
    CostSummary,
    CountryOut,
    IndustryOut,
    SpendPolicyOut,
    SpendPolicyUpdate,
    SpendStatus,
    ScoringRuleOut,
    ScoringRuleUpdate,
    ServiceCatalogOut,
)
from app.schemas.common import Message

router = APIRouter(prefix="/admin", tags=["Administration"])

# --- reference data (readable by any authenticated user) ------------------------

reference_router = APIRouter(prefix="/reference", tags=["Reference Data"])


@reference_router.get("/countries", response_model=list[CountryOut])
def list_countries(db: DbSession, _: CurrentUser, supported_only: bool = True) -> list[CountryOut]:
    stmt = select(Country).order_by(Country.name)
    if supported_only:
        stmt = stmt.where(Country.is_supported.is_(True))
    return [CountryOut.model_validate(r) for r in db.execute(stmt).scalars()]


@reference_router.get("/industries", response_model=list[IndustryOut])
def list_industries(db: DbSession, _: CurrentUser) -> list[IndustryOut]:
    rows = db.execute(
        select(Industry).where(Industry.is_active.is_(True)).order_by(Industry.name)
    ).scalars()
    return [IndustryOut.model_validate(r) for r in rows]


@reference_router.get("/services", response_model=list[ServiceCatalogOut])
def list_services(db: DbSession, _: CurrentUser) -> list[ServiceCatalogOut]:
    rows = db.execute(
        select(ServiceCatalogItem).where(ServiceCatalogItem.is_active.is_(True)).order_by(ServiceCatalogItem.name)
    ).scalars()
    return [ServiceCatalogOut.model_validate(r) for r in rows]


# --- providers and models -------------------------------------------------------


@router.get("/providers", response_model=list[AIProviderOut])
def list_providers(_: RequireAdmin, db: DbSession) -> list[AIProviderOut]:
    rows = db.execute(select(AIProvider).order_by(AIProvider.name)).scalars()
    return [AIProviderOut.model_validate(r) for r in rows]


@router.get("/models", response_model=list[AIModelOut])
def list_models(_: RequireAdmin, db: DbSession) -> list[AIModelOut]:
    rows = db.execute(select(AIModel).order_by(AIModel.tier, AIModel.display_name)).scalars()
    return [AIModelOut.model_validate(r) for r in rows]


@router.patch("/models/{model_id}", response_model=AIModelOut)
def update_model(model_id: str, payload: AIModelUpdate, admin: RequireAdmin, db: DbSession) -> AIModelOut:
    model = db.execute(select(AIModel).where(AIModel.model_id == model_id)).scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(model, field, value)
    audit(db, user=admin, action="admin.model_update", entity_type="ai_model", entity_id=model_id)
    db.commit()
    db.refresh(model)
    return AIModelOut.model_validate(model)


# --- API keys -------------------------------------------------------------------


@router.get("/api-keys", response_model=list[APIKeyOut])
def list_api_keys(admin: RequireAdmin, db: DbSession, organization_id: OrgId) -> list[APIKeyOut]:
    rows = db.execute(
        select(APIKey).where(APIKey.organization_id == organization_id).order_by(APIKey.created_at.desc())
    ).scalars()
    return [APIKeyOut.model_validate(r) for r in rows]


@router.post("/api-keys", response_model=APIKeyOut, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: APIKeyCreate, admin: RequireAdmin, db: DbSession, organization_id: OrgId
) -> APIKeyOut:
    """The raw value is encrypted immediately and never returned again."""
    key = APIKey(
        organization_id=organization_id,
        provider_slug=payload.provider_slug,
        label=payload.label,
        encrypted_value=encrypt_secret(payload.value),
        masked_hint=mask_secret(payload.value),
    )
    db.add(key)
    audit(db, user=admin, action="admin.api_key_create", entity_type="api_key", detail=payload.provider_slug)
    db.commit()
    db.refresh(key)
    return APIKeyOut.model_validate(key)


@router.delete("/api-keys/{key_id}", response_model=Message)
def delete_api_key(
    key_id: uuid.UUID, admin: RequireAdmin, db: DbSession, organization_id: OrgId
) -> Message:
    key = db.execute(
        select(APIKey).where(APIKey.id == key_id, APIKey.organization_id == organization_id)
    ).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    db.delete(key)
    audit(db, user=admin, action="admin.api_key_delete", entity_type="api_key", entity_id=str(key_id))
    db.commit()
    return Message(detail="API key deleted")


# --- connectors -----------------------------------------------------------------


@router.get("/connectors", response_model=list[ConnectorOut])
def list_connectors(_: RequireAdmin, db: DbSession) -> list[ConnectorOut]:
    rows = db.execute(select(Connector).order_by(Connector.name)).scalars()
    return [ConnectorOut.model_validate(r) for r in rows]


@router.get("/connectors/health", response_model=list[ConnectorHealth])
def connector_health(_: RequireAdmin) -> list[ConnectorHealth]:
    """Live check of which discovery sources can actually run right now."""
    return [ConnectorHealth(**status_) for status_ in connector_statuses()]


@router.patch("/connectors/{slug}", response_model=ConnectorOut)
def update_connector(
    slug: str, payload: ConnectorUpdate, admin: RequireAdmin, db: DbSession
) -> ConnectorOut:
    connector = db.execute(select(Connector).where(Connector.slug == slug)).scalar_one_or_none()
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(connector, field, value)
    audit(db, user=admin, action="admin.connector_update", entity_type="connector", entity_id=slug)
    db.commit()
    db.refresh(connector)
    return ConnectorOut.model_validate(connector)


# --- scoring --------------------------------------------------------------------


@router.get("/scoring-rules", response_model=list[ScoringRuleOut])
def list_scoring_rules(_: RequireAdmin, db: DbSession) -> list[ScoringRuleOut]:
    rows = db.execute(select(ScoringRule).order_by(ScoringRule.weight.desc())).scalars()
    return [ScoringRuleOut.model_validate(r) for r in rows]


@router.patch("/scoring-rules/{component}", response_model=list[ScoringRuleOut])
def update_scoring_rule(
    component: str, payload: ScoringRuleUpdate, admin: RequireAdmin, db: DbSession
) -> list[ScoringRuleOut]:
    rule = db.execute(
        select(ScoringRule).where(ScoringRule.component == component)
    ).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scoring component not found")
    rule.weight = payload.weight
    if payload.is_active is not None:
        rule.is_active = payload.is_active
    db.flush()

    rules = db.execute(select(ScoringRule)).scalars().all()
    total = sum(r.weight for r in rules if r.is_active)
    if round(total, 2) != 100.0:
        # The score must remain a 0-100 scale, so refuse an inconsistent weight set.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Active scoring weights must total 100; this change would make {total:.2f}.",
        )
    audit(db, user=admin, action="admin.scoring_update", entity_type="scoring_rule", entity_id=component)
    db.commit()
    return [
        ScoringRuleOut.model_validate(r)
        for r in db.execute(select(ScoringRule).order_by(ScoringRule.weight.desc())).scalars()
    ]


# --- cost -----------------------------------------------------------------------


@router.get("/costs", response_model=CostSummary)
def costs(
    _: RequireAdmin, db: DbSession, organization_id: OrgId, days: int = Query(30, ge=1, le=365)
) -> CostSummary:
    since = datetime.now(UTC) - timedelta(days=days)
    llm_cost = db.execute(
        select(func.sum(AIUsage.cost_usd)).where(
            AIUsage.organization_id == organization_id, AIUsage.created_at >= since
        )
    ).scalar_one() or 0.0
    prospects = db.execute(
        select(func.count(Company.id)).where(
            Company.organization_id == organization_id,
            Company.created_at >= since,
            Company.is_rejected.is_(False),
        )
    ).scalar_one()

    by_model = db.execute(
        select(
            AIUsage.model_id,
            func.sum(AIUsage.cost_usd),
            func.sum(AIUsage.input_tokens),
            func.sum(AIUsage.output_tokens),
        )
        .where(AIUsage.organization_id == organization_id, AIUsage.created_at >= since)
        .group_by(AIUsage.model_id)
    ).all()
    by_agent = db.execute(
        select(AIUsage.agent_key, func.sum(AIUsage.cost_usd), func.count(AIUsage.id))
        .where(AIUsage.organization_id == organization_id, AIUsage.created_at >= since)
        .group_by(AIUsage.agent_key)
    ).all()

    total = float(llm_cost)
    return CostSummary(
        period_days=days,
        llm_cost_usd=round(total, 4),
        connector_cost_usd=0.0,
        total_cost_usd=round(total, 4),
        prospects_produced=prospects,
        cost_per_prospect_usd=round(total / prospects, 4) if prospects else 0.0,
        by_model=[
            {
                "model": model,
                "cost_usd": round(float(cost or 0), 4),
                "input_tokens": int(inp or 0),
                "output_tokens": int(out or 0),
            }
            for model, cost, inp, out in by_model
        ],
        by_agent=[
            {"agent": key or "unknown", "cost_usd": round(float(cost or 0), 4), "calls": int(calls)}
            for key, cost, calls in by_agent
        ],
    )


# --- LLM spend policy ------------------------------------------------------


def _policy_row(db) -> SpendPolicyRow:
    """The single policy row, created with safe defaults on first read."""
    row = db.execute(select(SpendPolicyRow).limit(1)).scalar_one_or_none()
    if row is None:
        row = SpendPolicyRow()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _spend_status() -> dict:
    ledger = get_spend_ledger()
    llm = get_llm()
    status_payload = ledger.status()
    # Chains are reported so the UI can show exactly which models a change unlocks.
    free_chain: list[str] = []
    paid_chain: list[str] = []
    for tier in ("cheap", "smart"):
        for model in llm.chain_for(tier):
            target = free_chain if _is_free(model) else paid_chain
            if model not in target:
                target.append(model)
    status_payload["free_chain"] = free_chain
    status_payload["paid_chain"] = paid_chain
    return status_payload


def _is_free(model: str) -> bool:
    from app.llm.client import is_free_tier

    return is_free_tier(model)


@router.get("/spend-policy", response_model=SpendStatus)
def get_spend_policy(_: RequireAdmin, db: DbSession) -> SpendStatus:
    """Current ceiling plus live spend against it."""
    row = _policy_row(db)
    get_spend_ledger().cache_policy(
        SpendPolicy(
            allow_paid=row.allow_paid,
            daily_limit_usd=row.daily_limit_usd,
            monthly_limit_usd=row.monthly_limit_usd,
            alert_threshold_pct=row.alert_threshold_pct,
        )
    )
    return SpendStatus(**_spend_status())


@router.put("/spend-policy", response_model=SpendStatus)
def update_spend_policy(
    payload: SpendPolicyUpdate, admin: RequireAdmin, db: DbSession
) -> SpendStatus:
    """Change the ceiling. Takes effect across every worker within the cache TTL."""
    row = _policy_row(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, field, value)
    db.commit()
    db.refresh(row)

    policy = SpendPolicy(
        allow_paid=row.allow_paid,
        daily_limit_usd=row.daily_limit_usd,
        monthly_limit_usd=row.monthly_limit_usd,
        alert_threshold_pct=row.alert_threshold_pct,
    )
    get_spend_ledger().cache_policy(policy)
    audit(
        db,
        user=admin,
        action="llm_spend_policy_updated",
        entity_type="llm_spend_policy",
        detail=(
            f"paid={'on' if policy.allow_paid else 'off'} "
            f"daily=${policy.daily_limit_usd:.2f} monthly=${policy.monthly_limit_usd:.2f}"
        ),
    )
    db.commit()
    return SpendStatus(**_spend_status())


@router.get("/spend-status", response_model=SpendStatus)
def spend_status(_: RequireAdmin) -> SpendStatus:
    """Live spend meter. Cheap enough for the UI to poll."""
    return SpendStatus(**_spend_status())
