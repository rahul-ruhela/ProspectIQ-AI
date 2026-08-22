"""Agent registry, task queue, execution traces, inter-agent messages and memory."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONBType, TimestampMixin, UUIDMixin
from app.models.enums import AgentStatus, TaskStatus


class Agent(UUIDMixin, TimestampMixin, Base):
    """Persisted profile of an AI employee. Seeded from the code registry."""

    __tablename__ = "agents"

    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(160), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    tools: Mapped[list[str]] = mapped_column(JSONBType, default=list)
    input_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    model_tier: Mapped[str] = mapped_column(String(20), default="cheap", nullable=False)
    status: Mapped[AgentStatus] = mapped_column(
        String(32), default=AgentStatus.IDLE, nullable=False, index=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    total_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentTask(UUIDMixin, TimestampMixin, Base):
    """A unit of work the CEO orchestrator assigns to one AI employee."""

    __tablename__ = "agent_tasks"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    research_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    agent_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        String(32), default=TaskStatus.PENDING, nullable=False, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    confidence: Mapped[float | None] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    executions: Mapped[list["AgentExecution"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class AgentExecution(UUIDMixin, TimestampMixin, Base):
    """One attempt at a task, with timing, tokens and cost."""

    __tablename__ = "agent_executions"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True
    )
    agent_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    http_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    error: Mapped[str | None] = mapped_column(Text)

    task: Mapped[AgentTask] = relationship(back_populates="executions")


class AgentMessage(UUIDMixin, TimestampMixin, Base):
    """Message passed between agents through the orchestrator bus."""

    __tablename__ = "agent_messages"

    research_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    from_agent: Mapped[str] = mapped_column(String(80), nullable=False)
    to_agent: Mapped[str] = mapped_column(String(80), nullable=False)
    intent: Mapped[str] = mapped_column(String(80), nullable=False)
    body: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)


class AgentLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_logs"

    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    research_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    agent_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)


class AIMemory(UUIDMixin, TimestampMixin, Base):
    """Long-term memory shared by the department.

    ``embedding`` stays nullable so the platform runs without pgvector; when the
    extension is available the vector column is populated by the memory service.
    """

    __tablename__ = "ai_memory"

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    scope: Mapped[str] = mapped_column(String(60), default="global", nullable=False, index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    agent_key: Mapped[str | None] = mapped_column(String(80), index=True)
    key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONBType)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
