"""The AI-employee contract.

Every agent declares a name, role, goal, tools, input schema and output schema, and
returns a confidence score with its result. Execution is wrapped so that each attempt
produces an :class:`AgentExecution` row, structured logs and cost accounting — the
Agent Monitoring page is driven entirely by these records.
"""
from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.llm.client import CHEAP, LLMClient, LLMResult, LLMUsageTotals, get_llm
from app.models.agent import AgentExecution, AgentLog, AgentMessage, AgentTask
from app.models.agent import Agent as AgentModel
from app.models.admin import AIUsage
from app.models.enums import AgentStatus, TaskStatus

logger = get_logger(__name__)


@dataclass(slots=True)
class AgentContext:
    """Everything an agent needs to do its job and record what it did."""

    db: Session
    organization_id: uuid.UUID
    research_job_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    llm: LLMClient = field(default_factory=get_llm)
    usage: LLMUsageTotals = field(default_factory=LLMUsageTotals)
    connector_cost_usd: float = 0.0
    settings_overrides: dict[str, Any] = field(default_factory=dict)

    def for_company(self, company_id: uuid.UUID) -> "AgentContext":
        return AgentContext(
            db=self.db,
            organization_id=self.organization_id,
            research_job_id=self.research_job_id,
            campaign_id=self.campaign_id,
            company_id=company_id,
            llm=self.llm,
            usage=self.usage,
            settings_overrides=self.settings_overrides,
        )

    def record_llm(self, result: LLMResult, agent_key: str, purpose: str) -> None:
        """Persist token spend so budgets and cost-per-prospect stay truthful."""
        self.usage.add(result)
        if not result.model:
            return
        self.db.add(
            AIUsage(
                organization_id=self.organization_id,
                research_job_id=self.research_job_id,
                company_id=self.company_id,
                agent_key=agent_key,
                model_id=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                purpose=purpose,
            )
        )


@dataclass(slots=True)
class AgentResult:
    ok: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    error: str | None = None
    logs: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    http_requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @classmethod
    def failure(cls, error: str, **kwargs: Any) -> "AgentResult":
        return cls(ok=False, error=error, confidence=0.0, **kwargs)


class BaseAgent(ABC):
    """Base class for every AI employee."""

    key: str = "base"
    display_name: str = "Base Agent"
    role: str = "AI Worker"
    goal: str = ""
    tools: tuple[str, ...] = ()
    model_tier: str = CHEAP
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}
    output_schema: dict[str, Any] = {"type": "object", "properties": {}}
    max_attempts: int = 2

    def __init__(self) -> None:
        self._logs: list[str] = []

    # --- logging -----------------------------------------------------------
    def log(self, ctx: AgentContext, message: str, level: str = "info", **context: Any) -> None:
        self._logs.append(message)
        ctx.db.add(
            AgentLog(
                research_job_id=ctx.research_job_id,
                company_id=ctx.company_id,
                agent_key=self.key,
                level=level,
                message=message[:4000],
                context=context or None,
            )
        )
        logger.info("agent_log", agent=self.key, message=message, **context)

    def send(
        self, ctx: AgentContext, to_agent: str, intent: str, body: dict[str, Any]
    ) -> None:
        """Post a message on the orchestrator bus."""
        ctx.db.add(
            AgentMessage(
                research_job_id=ctx.research_job_id,
                company_id=ctx.company_id,
                from_agent=self.key,
                to_agent=to_agent,
                intent=intent,
                body=body,
            )
        )

    # --- contract ----------------------------------------------------------
    @abstractmethod
    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        """Do the work. Implementations must never fabricate data."""

    # --- execution wrapper -------------------------------------------------
    async def execute(
        self,
        ctx: AgentContext,
        payload: dict[str, Any],
        *,
        task: AgentTask | None = None,
        sequence: int = 0,
    ) -> AgentResult:
        """Run with retries, persisting the task, executions, timings and cost."""
        db = ctx.db
        if task is None:
            task = AgentTask(
                organization_id=ctx.organization_id,
                research_job_id=ctx.research_job_id,
                company_id=ctx.company_id,
                agent_key=self.key,
                sequence=sequence,
                payload=_jsonable(payload),
                status=TaskStatus.ASSIGNED,
                max_attempts=self.max_attempts,
            )
            db.add(task)
            db.flush()

        profile = db.query(AgentModel).filter(AgentModel.key == self.key).one_or_none()
        if profile is not None and not profile.is_enabled:
            task.status = TaskStatus.SKIPPED
            task.error = "agent_disabled"
            db.flush()
            return AgentResult.failure("agent_disabled")

        self._logs = []
        result = AgentResult.failure("not_run")

        for attempt in range(1, self.max_attempts + 1):
            task.attempts = attempt
            task.status = TaskStatus.RUNNING
            task.started_at = task.started_at or datetime.now(UTC)
            if profile is not None:
                profile.status = AgentStatus.RUNNING
            db.flush()

            started = time.monotonic()
            try:
                result = await self.run(ctx, payload)
            except Exception as exc:  # an agent failure must never kill the department
                logger.exception("agent_crashed", agent=self.key)
                result = AgentResult.failure(f"{type(exc).__name__}: {exc}")
            duration_ms = int((time.monotonic() - started) * 1000)

            db.add(
                AgentExecution(
                    task_id=task.id,
                    agent_key=self.key,
                    attempt=attempt,
                    status=TaskStatus.COMPLETED if result.ok else TaskStatus.FAILED,
                    duration_ms=duration_ms,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_usd=result.cost_usd,
                    http_requests=result.http_requests,
                    output=_jsonable(result.data) if result.ok else None,
                    error=result.error,
                )
            )
            if profile is not None:
                profile.total_runs += 1
                profile.last_run_at = datetime.now(UTC)
                profile.avg_duration_ms = int(
                    (profile.avg_duration_ms * (profile.total_runs - 1) + duration_ms)
                    / profile.total_runs
                )
                if result.ok:
                    profile.avg_confidence = round(
                        (profile.avg_confidence * (profile.total_runs - 1) + result.confidence)
                        / profile.total_runs,
                        4,
                    )
                else:
                    profile.total_failures += 1

            if result.ok:
                break

        task.status = TaskStatus.COMPLETED if result.ok else TaskStatus.FAILED
        task.result = _jsonable(result.data) if result.ok else None
        task.confidence = result.confidence
        task.error = result.error
        task.finished_at = datetime.now(UTC)
        if profile is not None:
            profile.status = AgentStatus.COMPLETED if result.ok else AgentStatus.FAILED
        db.flush()
        return result

    def describe(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "role": self.role,
            "goal": self.goal,
            "tools": list(self.tools),
            "model_tier": self.model_tier,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


def _jsonable(value: Any) -> Any:
    """Coerce a payload into something JSON columns accept."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (uuid.UUID, datetime)):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
