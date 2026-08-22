"""Agent monitoring schemas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import AgentStatus, TaskStatus
from app.schemas.common import ORMModel


class AgentOut(ORMModel):
    id: uuid.UUID
    key: str
    display_name: str
    role: str
    goal: str
    tools: list[str]
    model_tier: str
    status: AgentStatus
    is_enabled: bool
    total_runs: int
    total_failures: int
    avg_confidence: float
    avg_duration_ms: int
    last_run_at: datetime | None


class AgentDetail(AgentOut):
    input_schema: dict[str, Any] | None
    output_schema: dict[str, Any] | None


class AgentTaskOut(ORMModel):
    id: uuid.UUID
    agent_key: str
    research_job_id: uuid.UUID | None
    company_id: uuid.UUID | None
    sequence: int
    status: TaskStatus
    priority: int
    confidence: float | None
    attempts: int
    max_attempts: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class AgentTaskDetail(AgentTaskOut):
    payload: dict[str, Any] | None
    result: dict[str, Any] | None


class AgentExecutionOut(ORMModel):
    id: uuid.UUID
    agent_key: str
    attempt: int
    status: TaskStatus
    duration_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    http_requests: int
    error: str | None
    created_at: datetime


class AgentLogOut(ORMModel):
    id: uuid.UUID
    agent_key: str
    level: str
    message: str
    context: dict[str, Any] | None
    company_id: uuid.UUID | None
    created_at: datetime


class AgentMessageOut(ORMModel):
    id: uuid.UUID
    from_agent: str
    to_agent: str
    intent: str
    body: dict[str, Any] | None
    created_at: datetime


class AgentToggle(BaseModel):
    is_enabled: bool


class DepartmentStatus(BaseModel):
    """Live snapshot rendered by the Agent Monitoring page."""

    agents: list[AgentOut]
    running_tasks: int
    pending_tasks: int
    failed_tasks_24h: int
    active_jobs: int
    tasks_by_status: dict[str, int] = Field(default_factory=dict)
