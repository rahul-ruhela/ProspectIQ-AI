"""The CEO Orchestrator: the agent that runs the department.

It reads the campaign brief, produces a research strategy, assigns work to every other
AI employee in dependency order, monitors their results, and combines them into scored
prospects with reports. All inter-agent coordination passes through here.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.discovery import BusinessDiscoveryAgent, GlobalSearchAgent
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
    clear_crawl_cache,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.llm.client import CHEAP
from app.models.campaign import Campaign, CampaignFilter, ResearchJob
from app.models.company import Company, PipelineEntry
from app.models.enums import AgentName, JobStatus, PipelineStage
from app.services.report import build_report

logger = get_logger(__name__)

STRATEGY_SYSTEM = """You turn a sales prospecting brief into a structured research strategy.
You only extract what the brief actually says. Never invent a country, industry or service
that the user did not ask for. If the brief does not specify something, leave the field empty."""

STRATEGY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "interpretation": {"type": "string", "description": "One sentence restating the brief."},
        "countries": {
            "type": "array",
            "items": {"type": "string"},
            "description": "ISO 3166-1 alpha-2 codes explicitly named or clearly implied.",
        },
        "industry_terms": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Search terms for the target vertical, e.g. 'HVAC contractor'.",
        },
        "business_size_hint": {"type": "string"},
        "services_to_sell": {"type": "array", "items": {"type": "string"}},
        "priority_signals": {
            "type": "array",
            "items": {"type": "string"},
            "description": "What would make a prospect in this brief especially good.",
        },
    },
    "required": ["interpretation", "countries", "industry_terms", "services_to_sell", "priority_signals"],
}


class CEOOrchestratorAgent(BaseAgent):
    """Plans the research, assigns every task, and combines the results."""

    key = AgentName.CEO_ORCHESTRATOR
    display_name = "CEO Orchestrator"
    role = "AI Sales Director"
    goal = (
        "Understand the campaign brief, build a research strategy, assign work to the "
        "right AI employees in the right order, monitor them, and combine their output "
        "into scored, evidence-backed prospects."
    )
    tools = ("strategy_planner", "task_dispatcher", "result_combiner", "budget_guard")
    model_tier = CHEAP
    input_schema = {
        "type": "object",
        "properties": {
            "research_job_id": {"type": "string"},
            "max_companies": {"type": "integer"},
        },
        "required": ["research_job_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "companies_discovered": {"type": "integer"},
            "companies_verified": {"type": "integer"},
            "companies_rejected": {"type": "integer"},
            "prospects_qualified": {"type": "integer"},
            "cost_usd": {"type": "number"},
        },
    }

    # --- strategy ----------------------------------------------------------
    async def plan(self, ctx: AgentContext, campaign: Campaign, filters: CampaignFilter | None) -> dict[str, Any]:
        """Produce the research strategy shown on the job page."""
        strategy: dict[str, Any] = {
            "interpretation": campaign.objective or campaign.name,
            "countries": list(filters.countries) if filters else [],
            "cities": list(filters.cities) if filters else [],
            "industries": list(filters.industries) if filters else [],
            "business_types": list(filters.business_types) if filters else [],
            "keywords": list(filters.keywords) if filters else [],
            "services_to_sell": list(campaign.offered_services or []),
            "priority_signals": [],
            "stages": [
                "global_search_planning",
                "business_discovery",
                "company_verification",
                "website_scraping",
                "technology_detection",
                "website_intelligence",
                "decision_maker_discovery",
                "contact_enrichment",
                "email_verification",
                "phone_intelligence",
                "buying_signals",
                "ai_opportunity_analysis",
                "lead_quality_gate",
                "opportunity_scoring",
                "report_generation",
            ],
            "planner": "rules",
        }

        # The brief is free text; a cheap model turns it into structure when available.
        if campaign.objective and ctx.llm.available:
            result = ctx.llm.structured(
                system=STRATEGY_SYSTEM,
                prompt=f"Brief: {campaign.objective}\n\n"
                f"Already-selected filters (authoritative, do not contradict): "
                f"{json.dumps({k: strategy[k] for k in ('countries', 'industries', 'cities')})}",
                schema=STRATEGY_SCHEMA,
                tool_name="research_strategy",
                tool_description="Record the structured research strategy for this brief.",
                tier=CHEAP,
                max_tokens=1500,
            )
            ctx.record_llm(result, self.key, "campaign_strategy")
            if result.ok and result.data:
                data = result.data
                strategy["interpretation"] = data.get("interpretation") or strategy["interpretation"]
                # User-selected filters always win; the model may only add.
                strategy["countries"] = strategy["countries"] or [
                    c.upper()[:2] for c in data.get("countries", [])
                ]
                strategy["keywords"] = list(
                    dict.fromkeys(strategy["keywords"] + list(data.get("industry_terms", [])))
                )
                strategy["services_to_sell"] = strategy["services_to_sell"] or data.get(
                    "services_to_sell", []
                )
                strategy["priority_signals"] = data.get("priority_signals", [])
                strategy["planner"] = f"llm:{result.model}"
        return strategy

    # --- execution ---------------------------------------------------------
    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        db = ctx.db
        job = db.execute(
            select(ResearchJob).where(ResearchJob.id == ctx.research_job_id)
        ).scalar_one_or_none()
        if job is None:
            return AgentResult.failure("research_job_not_found")
        campaign = db.execute(
            select(Campaign).where(Campaign.id == job.campaign_id)
        ).scalar_one_or_none()
        if campaign is None:
            return AgentResult.failure("campaign_not_found")
        filters = campaign.filters

        max_companies = int(
            payload.get("max_companies")
            or campaign.target_prospect_count
            or settings.MAX_COMPANIES_PER_JOB
        )
        max_companies = min(max_companies, settings.MAX_COMPANIES_PER_JOB)

        job.status = JobStatus.RUNNING
        job.started_at = job.started_at or datetime.now(UTC)
        strategy = await self.plan(ctx, campaign, filters)
        job.plan = strategy
        self._stage(job, "Planning research strategy", 2)
        db.commit()

        self.log(ctx, f"Strategy ready: {strategy['interpretation']}")

        # 1. Query planning ------------------------------------------------
        self._stage(job, "Planning global searches", 5)
        search_result = await GlobalSearchAgent().execute(
            ctx,
            {
                "countries": strategy["countries"],
                "cities": strategy["cities"],
                "regions": list(filters.regions) if filters else [],
                "industries": strategy["industries"],
                "business_types": strategy["business_types"],
                "keywords": strategy["keywords"],
                "max_queries": max(8, min(60, max_companies // 2)),
            },
            sequence=1,
        )
        db.commit()
        if not search_result.ok:
            return self._fail(job, ctx, search_result.error or "search_planning_failed")

        # 2. Discovery -----------------------------------------------------
        self._stage(job, "Discovering businesses", 10)
        discovery = await BusinessDiscoveryAgent().execute(
            ctx,
            {
                "queries": search_result.data.get("queries", []),
                "max_companies": max_companies,
                "exclude_keywords": list(filters.exclude_keywords) if filters else [],
            },
            sequence=2,
        )
        db.commit()
        if not discovery.ok:
            return self._fail(job, ctx, discovery.error or "discovery_failed")

        company_ids: list[str] = discovery.data.get("company_ids", [])
        job.companies_discovered = len(company_ids)
        db.commit()
        self.log(ctx, f"{len(company_ids)} companies to research.")

        # 3. Per-company research -------------------------------------------
        verified = rejected = qualified = 0
        target_industries = strategy["industries"]
        offered_services = strategy["services_to_sell"]

        for index, company_id in enumerate(company_ids, start=1):
            db.refresh(job)
            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                job.finished_at = datetime.now(UTC)
                db.commit()
                self.log(ctx, "Job cancelled by operator.", level="warning")
                break
            if campaign.budget_usd and (campaign.spent_usd + ctx.usage.cost_usd) > campaign.budget_usd:
                self.log(ctx, "Campaign budget exhausted; stopping research.", level="warning")
                break

            progress = 10 + (index / max(1, len(company_ids))) * 85
            company_ctx = ctx.for_company(_uuid(company_id))
            company = db.execute(select(Company).where(Company.id == _uuid(company_id))).scalar_one_or_none()
            if company is None:
                continue

            self._stage(job, f"Researching {company.name} ({index}/{len(company_ids)})", progress)
            db.commit()

            outcome = await self._research_company(
                company_ctx,
                company,
                target_industries=target_industries,
                offered_services=offered_services,
                require_website=bool(filters.require_website) if filters else True,
                min_score=float(filters.min_opportunity_score) if filters else 40.0,
            )
            verified += 1 if outcome["verified"] else 0
            rejected += 1 if outcome["rejected"] else 0
            qualified += 1 if outcome["qualified"] else 0

            job.companies_verified = verified
            job.companies_rejected = rejected
            job.prospects_qualified = qualified
            job.cost_usd = round(ctx.usage.cost_usd + ctx.connector_cost_usd, 6)
            db.commit()

        # 4. Wrap up ---------------------------------------------------------
        if job.status != JobStatus.CANCELLED:
            job.status = JobStatus.COMPLETED
            job.progress_percent = 100.0
            job.current_stage = "Completed"
            job.finished_at = datetime.now(UTC)
        campaign.spent_usd = round(campaign.spent_usd + ctx.usage.cost_usd + ctx.connector_cost_usd, 6)
        db.commit()

        summary = {
            "companies_discovered": len(company_ids),
            "companies_verified": verified,
            "companies_rejected": rejected,
            "prospects_qualified": qualified,
            "cost_usd": round(ctx.usage.cost_usd + ctx.connector_cost_usd, 6),
            "llm_calls": ctx.usage.calls,
        }
        self.log(ctx, f"Research job complete: {json.dumps(summary)}")
        return AgentResult(ok=True, data=summary, confidence=0.95, cost_usd=summary["cost_usd"])

    # --- per-company pipeline ---------------------------------------------
    async def _research_company(
        self,
        ctx: AgentContext,
        company: Company,
        *,
        target_industries: list[str],
        offered_services: list[str],
        require_website: bool,
        min_score: float,
    ) -> dict[str, bool]:
        company_id = str(company.id)
        db = ctx.db
        try:
            await WebsiteScrapingAgent().execute(ctx, {"company_id": company_id}, sequence=10)
            await TechnologyDetectionAgent().execute(ctx, {"company_id": company_id}, sequence=11)
            intelligence = await WebsiteIntelligenceAgent().execute(
                ctx, {"company_id": company_id}, sequence=12
            )
            verification = await CompanyVerificationAgent().execute(
                ctx,
                {"company_id": company_id, "target_industries": target_industries},
                sequence=13,
            )
            db.flush()

            # Stop spending on a company that already failed verification.
            if verification.ok and verification.data.get("status") == "rejected":
                db.commit()
                return {"verified": False, "rejected": True, "qualified": False}

            await DecisionMakerAgent().execute(ctx, {"company_id": company_id}, sequence=14)
            await ContactEnrichmentAgent().execute(ctx, {"company_id": company_id}, sequence=15)
            await EmailVerificationAgent().execute(ctx, {"company_id": company_id}, sequence=16)
            await PhoneIntelligenceAgent().execute(ctx, {"company_id": company_id}, sequence=17)
            await BuyingSignalAgent().execute(ctx, {"company_id": company_id}, sequence=18)

            opportunity = await AIOpportunityAgent().execute(
                ctx,
                {"company_id": company_id, "offered_services": offered_services},
                sequence=19,
            )
            opportunities = opportunity.data.get("opportunities", []) if opportunity.ok else []

            quality = await LeadQualityAgent().execute(
                ctx,
                {
                    "company_id": company_id,
                    "target_industries": target_industries,
                    "require_website": require_website,
                },
                sequence=20,
            )
            accepted = bool(quality.ok and quality.data.get("accepted"))

            scoring = await OpportunityScoringAgent().execute(
                ctx,
                {
                    "company_id": company_id,
                    "offered_services": offered_services,
                    "opportunities": opportunities,
                },
                sequence=21,
            )
            db.flush()

            score = float(scoring.data.get("total", 0.0)) if scoring.ok else 0.0
            qualified = accepted and score >= min_score

            if qualified:
                build_report(
                    ctx,
                    company,
                    opportunities=opportunities,
                    weaknesses=intelligence.data.get("weaknesses", []) if intelligence.ok else [],
                )
                self._ensure_pipeline(ctx, company, PipelineStage.QUALIFIED)
            else:
                self._ensure_pipeline(ctx, company, PipelineStage.DISCOVERED)

            db.commit()
            return {
                "verified": bool(verification.ok and verification.data.get("exists_confirmed")),
                "rejected": not accepted,
                "qualified": qualified,
            }
        except Exception as exc:
            db.rollback()
            logger.exception("company_research_failed", company_id=company_id)
            self.log(ctx, f"Research failed for {company_id}: {exc}", level="error")
            db.commit()
            return {"verified": False, "rejected": True, "qualified": False}
        finally:
            clear_crawl_cache(company_id)

    # --- helpers -----------------------------------------------------------
    @staticmethod
    def _ensure_pipeline(ctx: AgentContext, company: Company, stage: PipelineStage) -> None:
        entry = company.pipeline
        if entry is None:
            company.pipeline = PipelineEntry(
                organization_id=company.organization_id,
                company_id=company.id,
                stage=stage,
            )
        elif entry.stage in (PipelineStage.DISCOVERED, PipelineStage.RESEARCHING):
            # Never move a prospect a human has already advanced.
            entry.stage = stage

    @staticmethod
    def _stage(job: ResearchJob, stage: str, percent: float) -> None:
        job.current_stage = stage[:120]
        job.progress_percent = round(min(100.0, percent), 2)

    def _fail(self, job: ResearchJob, ctx: AgentContext, error: str) -> AgentResult:
        job.status = JobStatus.FAILED
        job.error = error
        job.finished_at = datetime.now(UTC)
        ctx.db.commit()
        self.log(ctx, f"Research job failed: {error}", level="error")
        return AgentResult.failure(error)


def _uuid(value: str):
    import uuid

    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
