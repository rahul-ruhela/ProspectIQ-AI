"""The AI department roster.

The registry is the single source of truth for which agents exist. Seeding copies it
into the ``agents`` table so the Agent Monitoring UI, the admin toggles and the task
dispatcher all agree on the same roster.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.base import BaseAgent
from app.agents.discovery import BusinessDiscoveryAgent, GlobalSearchAgent
from app.agents.orchestrator import CEOOrchestratorAgent
from app.agents.people import (
    ContactEnrichmentAgent,
    DecisionMakerAgent,
    EmailVerificationAgent,
    PhoneIntelligenceAgent,
)
from app.agents.quality import (
    CompanyVerificationAgent,
    LeadQualityAgent,
    OpportunityScoringAgent,
)
from app.agents.signals import AIOpportunityAgent, BuyingSignalAgent
from app.agents.website import (
    TechnologyDetectionAgent,
    WebsiteIntelligenceAgent,
    WebsiteScrapingAgent,
)
from app.models.agent import Agent as AgentModel

AGENT_CLASSES: tuple[type[BaseAgent], ...] = (
    CEOOrchestratorAgent,
    BusinessDiscoveryAgent,
    GlobalSearchAgent,
    WebsiteScrapingAgent,
    WebsiteIntelligenceAgent,
    TechnologyDetectionAgent,
    AIOpportunityAgent,
    DecisionMakerAgent,
    ContactEnrichmentAgent,
    EmailVerificationAgent,
    PhoneIntelligenceAgent,
    BuyingSignalAgent,
    CompanyVerificationAgent,
    LeadQualityAgent,
    OpportunityScoringAgent,
)

AGENTS_BY_KEY: dict[str, type[BaseAgent]] = {cls.key: cls for cls in AGENT_CLASSES}


def get_agent(key: str) -> BaseAgent | None:
    cls = AGENTS_BY_KEY.get(key)
    return cls() if cls else None


def describe_all() -> list[dict]:
    return [cls().describe() for cls in AGENT_CLASSES]


def sync_registry(db: Session) -> int:
    """Insert or refresh the agent profile rows. Idempotent."""
    changed = 0
    for cls in AGENT_CLASSES:
        agent = cls()
        profile = db.query(AgentModel).filter(AgentModel.key == agent.key).one_or_none()
        if profile is None:
            profile = AgentModel(key=agent.key)
            db.add(profile)
            changed += 1
        profile.display_name = agent.display_name
        profile.role = agent.role
        profile.goal = agent.goal
        profile.tools = list(agent.tools)
        profile.input_schema = agent.input_schema
        profile.output_schema = agent.output_schema
        profile.model_tier = agent.model_tier
    db.flush()
    return changed
