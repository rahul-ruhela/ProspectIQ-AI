"""Idempotent seeding of reference data, the agent roster and the first admin user."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.registry import sync_registry
from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.admin import AIModel, AIProvider, Connector, ScoringRule, ServiceCatalogItem
from app.models.enums import UserRole
from app.models.geo import Country, Industry
from app.models.org import Organization, Permission, Role, User
from app.seed.data import AI_MODELS, AI_PROVIDERS, CONNECTORS, COUNTRIES, INDUSTRIES, SERVICES
from app.services.scoring import DEFAULT_WEIGHTS, WEIGHT_DESCRIPTIONS

logger = get_logger(__name__)

PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("campaign:read", "View campaigns"),
    ("campaign:write", "Create and edit campaigns"),
    ("research:run", "Start and control research jobs"),
    ("company:read", "View companies and reports"),
    ("company:write", "Edit, reject and re-score companies"),
    ("crm:read", "View the CRM pipeline"),
    ("crm:write", "Move prospects and log outreach"),
    ("report:approve", "Approve reports for human outreach"),
    ("admin:manage", "Manage users, providers, connectors and scoring"),
    ("export:data", "Export prospect data"),
)

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    UserRole.ADMIN: tuple(code for code, _ in PERMISSIONS),
    UserRole.RESEARCHER: (
        "campaign:read", "campaign:write", "research:run", "company:read",
        "company:write", "crm:read", "crm:write", "export:data",
    ),
    UserRole.SALES_USER: (
        "campaign:read", "company:read", "crm:read", "crm:write",
        "report:approve", "export:data",
    ),
    UserRole.VIEWER: ("campaign:read", "company:read", "crm:read"),
}


def seed_permissions_and_roles(db: Session) -> None:
    existing = {p.code: p for p in db.execute(select(Permission)).scalars()}
    for code, description in PERMISSIONS:
        if code not in existing:
            permission = Permission(code=code, description=description)
            db.add(permission)
            existing[code] = permission
    db.flush()

    roles = {r.name: r for r in db.execute(select(Role)).scalars()}
    for role_name, codes in ROLE_PERMISSIONS.items():
        role = roles.get(str(role_name))
        if role is None:
            role = Role(name=str(role_name), description=f"{role_name} role")
            db.add(role)
            db.flush()
        role.permissions = [existing[code] for code in codes if code in existing]
    db.flush()


def seed_countries(db: Session) -> int:
    known = {c.iso2 for c in db.execute(select(Country)).scalars()}
    added = 0
    for iso2, iso3, name, continent, phone, language in COUNTRIES:
        if iso2 in known:
            continue
        db.add(
            Country(
                iso2=iso2,
                iso3=iso3,
                name=name,
                continent=continent,
                phone_code=phone,
                default_language=language,
                is_supported=True,
            )
        )
        added += 1
    db.flush()
    return added


def seed_industries(db: Session) -> int:
    known = {i.slug: i for i in db.execute(select(Industry)).scalars()}
    added = 0
    for slug, name, naics, keywords, fit in INDUSTRIES:
        industry = known.get(slug)
        if industry is None:
            industry = Industry(slug=slug)
            db.add(industry)
            added += 1
        industry.name = name
        industry.naics_code = naics
        industry.search_keywords = keywords
        industry.ai_fit_baseline = fit
        industry.is_active = True
    db.flush()
    return added


def seed_services(db: Session) -> int:
    known = {s.slug: s for s in db.execute(select(ServiceCatalogItem)).scalars()}
    added = 0
    for slug, name, description, deal, triggers in SERVICES:
        item = known.get(slug)
        if item is None:
            item = ServiceCatalogItem(slug=slug)
            db.add(item)
            added += 1
        item.name = name
        item.description = description
        item.typical_deal_usd = deal
        item.trigger_features = list(triggers)
        item.is_active = True
    db.flush()
    return added


def seed_providers_and_models(db: Session) -> None:
    existing = {p.slug for p in db.execute(select(AIProvider)).scalars()}
    for slug, name, base_url in AI_PROVIDERS:
        if slug not in existing:
            db.add(AIProvider(slug=slug, name=name, base_url=base_url, is_enabled=True))
    known = {m.model_id: m for m in db.execute(select(AIModel)).scalars()}
    for provider_slug, model_id, display, tier, cost_in, cost_out, max_out in AI_MODELS:
        model = known.get(model_id)
        if model is None:
            model = AIModel(model_id=model_id)
            db.add(model)
        model.provider_slug = provider_slug
        model.display_name = display
        model.tier = tier
        model.input_cost_per_mtok = cost_in
        model.output_cost_per_mtok = cost_out
        model.max_output_tokens = max_out
        model.is_enabled = True
    db.flush()


def seed_connectors(db: Session) -> None:
    known = {c.slug: c for c in db.execute(select(Connector)).scalars()}
    for slug, name, kind, requires_key, cost, notes in CONNECTORS:
        connector = known.get(slug)
        if connector is None:
            connector = Connector(slug=slug)
            db.add(connector)
        connector.name = name
        connector.kind = kind
        connector.requires_api_key = requires_key
        connector.cost_per_call_usd = cost
        connector.notes = notes
    db.flush()


def seed_scoring_rules(db: Session) -> None:
    known = {r.component: r for r in db.execute(select(ScoringRule)).scalars()}
    for component, weight in DEFAULT_WEIGHTS.items():
        rule = known.get(component)
        if rule is None:
            rule = ScoringRule(component=component)
            db.add(rule)
        rule.weight = weight
        rule.description = WEIGHT_DESCRIPTIONS.get(component)
        rule.is_active = True
    db.flush()


def seed_admin_user(db: Session) -> str | None:
    """Create the bootstrap admin from the environment, if configured and absent."""
    email = settings.SEED_ADMIN_EMAIL.strip().lower()
    password = settings.SEED_ADMIN_PASSWORD
    if not email or not password:
        return None
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        return None
    if len(password) < 10:
        logger.warning("seed_admin_password_too_short")
        return None

    org_name = settings.SEED_ORG_NAME
    organization = db.execute(
        select(Organization).where(Organization.slug == "prospectiq")
    ).scalar_one_or_none()
    if organization is None:
        organization = Organization(name=org_name, slug="prospectiq")
        db.add(organization)
        db.flush()

    db.add(
        User(
            organization_id=organization.id,
            email=email,
            password_hash=hash_password(password),
            full_name=settings.SEED_ADMIN_NAME,
            role=UserRole.ADMIN,
        )
    )
    db.flush()
    return email


def run_seed() -> dict:
    """Seed everything. Safe to run repeatedly."""
    with session_scope() as db:
        seed_permissions_and_roles(db)
        countries = seed_countries(db)
        industries = seed_industries(db)
        services = seed_services(db)
        seed_providers_and_models(db)
        seed_connectors(db)
        seed_scoring_rules(db)
        agents = sync_registry(db)
        admin_email = seed_admin_user(db)

    summary = {
        "countries_added": countries,
        "industries_added": industries,
        "services_added": services,
        "agents_registered": agents,
        "admin_created": admin_email,
    }
    logger.info("seed_complete", **{k: str(v) for k, v in summary.items()})
    return summary


if __name__ == "__main__":
    import json

    print(json.dumps(run_seed(), indent=2))
