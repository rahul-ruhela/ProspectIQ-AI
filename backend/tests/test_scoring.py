"""Tests for the opportunity scoring engine and its explainability guarantees."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.company import Company, OpportunityScore, Website, WebsiteFeature
from app.models.enums import Certainty, ScoreCategory, ServiceOffering
from app.services.scoring import (
    DEFAULT_WEIGHTS,
    compute_completeness,
    score_company,
    stamp_score,
)


@pytest.fixture()
def db() -> Session:
    # SQLite is enough here: the scoring engine only reads ORM objects.
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _company(db: Session, **kwargs) -> Company:
    company = Company(
        organization_id=uuid.uuid4(),
        name=kwargs.pop("name", "Acme HVAC"),
        domain=kwargs.pop("domain", "acmehvac.com"),
        website="https://acmehvac.com",
        industry_slug=kwargs.pop("industry_slug", None),
        confidence=kwargs.pop("confidence", 0.7),
        **kwargs,
    )
    db.add(company)
    db.flush()
    return company


def _website(db: Session, company: Company, *, quality: float, missing: list[str]) -> Website:
    website = Website(
        company_id=company.id,
        url=company.website,
        is_reachable=True,
        is_https=True,
        quality_score=quality,
    )
    for key in missing:
        website.features.append(
            WebsiteFeature(feature_key=key, present=False, certainty=Certainty.OBSERVED)
        )
    company.website_record = website
    db.flush()
    return website


def test_weights_total_one_hundred() -> None:
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(100.0)


def test_score_stays_within_zero_to_one_hundred(db: Session) -> None:
    company = _company(db)
    _website(db, company, quality=0.0, missing=list(DEFAULT_WEIGHTS))
    outcome = score_company(db, company)
    assert 0.0 <= outcome.total <= 100.0


def test_every_component_carries_its_reasoning(db: Session) -> None:
    """The score must be auditable: no component may be a bare number."""
    company = _company(db)
    _website(db, company, quality=45.0, missing=["contact_form", "live_chat"])
    outcome = score_company(db, company)

    assert set(outcome.components) == set(DEFAULT_WEIGHTS)
    for key, component in outcome.components.items():
        assert component.reasons, f"{key} produced no explanation"
        assert component.points <= component.weight + 1e-9


def test_a_worse_website_scores_a_bigger_opportunity(db: Session) -> None:
    good = _company(db, domain="good.com", name="Good Co")
    _website(db, good, quality=95.0, missing=[])
    bad = _company(db, domain="bad.com", name="Bad Co")
    _website(db, bad, quality=20.0, missing=["contact_form", "live_chat", "online_booking"])

    assert score_company(db, bad).total > score_company(db, good).total


def test_service_match_only_counts_services_the_campaign_sells(db: Session) -> None:
    company = _company(db)
    _website(db, company, quality=50.0, missing=["online_booking"])
    opportunities = [
        {"service": str(ServiceOffering.AI_AUTOMATION), "certainty": "observed", "statement": "x"}
    ]

    matched = score_company(
        db, company, offered_services=[str(ServiceOffering.AI_AUTOMATION)], opportunities=opportunities
    )
    unmatched = score_company(
        db, company, offered_services=[str(ServiceOffering.MOBILE_APPLICATION)], opportunities=opportunities
    )
    assert matched.components["service_match"].points > unmatched.components["service_match"].points
    assert matched.recommended_services == [str(ServiceOffering.AI_AUTOMATION)]
    assert unmatched.recommended_services == []


def test_unknown_employee_count_is_scored_neutrally_not_assumed(db: Session) -> None:
    company = _company(db)
    outcome = score_company(db, company)
    component = outcome.components["company_size"]
    assert component.normalised == 0.5
    assert any("unknown" in reason.lower() for reason in component.reasons)


def test_stamp_score_writes_the_breakdown_to_the_company(db: Session) -> None:
    company = _company(db)
    _website(db, company, quality=40.0, missing=["contact_form"])
    outcome = score_company(db, company)
    stamp_score(company, outcome)

    assert isinstance(company.score, OpportunityScore)
    assert company.opportunity_score == outcome.total
    assert company.opportunity_category == outcome.category
    assert set(company.score.breakdown) == set(DEFAULT_WEIGHTS)
    assert company.last_researched_at is not None


def test_completeness_grows_as_facts_are_established(db: Session) -> None:
    company = _company(db, industry_slug=None)
    before = compute_completeness(company)

    company.industry_slug = "hvac"
    company.country_code = "US"
    company.city = "Austin"
    company.description = "Heating and cooling"
    company.website_active = True
    after = compute_completeness(company)

    assert after > before
    assert 0.0 <= after <= 1.0


def test_category_boundaries(db: Session) -> None:
    assert ScoreCategory.from_score(74.9) == ScoreCategory.MEDIUM
    assert ScoreCategory.from_score(59.9) == ScoreCategory.LOW
    assert ScoreCategory.from_score(39.9) == ScoreCategory.POOR
