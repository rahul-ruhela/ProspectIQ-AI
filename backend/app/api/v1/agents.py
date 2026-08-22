"""Agent monitoring: roster, live status, tasks, executions, logs and the message bus."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbSession, OrgId, RequireAdmin, audit
from app.models.agent import Agent, AgentExecution, AgentLog, AgentMessage, AgentTask
from app.models.campaign import ResearchJob
from app.models.enums import AgentStatus, JobStatus, TaskStatus
from app.schemas.agent import (
    AgentDetail,
    AgentExecutionOut,
    AgentLogOut,
    AgentMessageOut,
    AgentOut,
    AgentTaskDetail,
    AgentTaskOut,
    AgentToggle,
    DepartmentStatus,
)
from app.schemas.common import Page

router = APIRouter(prefix="/agents", tags=["AI Employees"])


@router.get("", response_model=list[AgentOut])
def list_agents(db: DbSession, _: CurrentUser) -> list[AgentOut]:
    rows = db.execute(select(Agent).order_by(Agent.created_at)).scalars().all()
    return [AgentOut.model_validate(row) for row in rows]


@router.get("/status", response_model=DepartmentStatus)
def department_status(db: DbSession, organization_id: OrgId, _: CurrentUser) -> DepartmentStatus:
    """Everything the Agent Monitoring page renders, in one call."""
    agents = db.execute(select(Agent).order_by(Agent.created_at)).scalars().all()
    since = datetime.now(UTC) - timedelta(hours=24)

    counts = dict(
        db.execute(
            select(AgentTask.status, func.count(AgentTask.id))
            .where(AgentTask.organization_id == organization_id)
            .group_by(AgentTask.status)
        ).all()
    )
    failed_24h = db.execute(
        select(func.count(AgentTask.id)).where(
            AgentTask.organization_id == organization_id,
            AgentTask.status == TaskStatus.FAILED,
            AgentTask.created_at >= since,
        )
    ).scalar_one()
    active_jobs = db.execute(
        select(func.count(ResearchJob.id)).where(
            ResearchJob.organization_id == organization_id,
            ResearchJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    ).scalar_one()

    return DepartmentStatus(
        agents=[AgentOut.model_validate(a) for a in agents],
        running_tasks=int(counts.get(TaskStatus.RUNNING, 0)),
        pending_tasks=int(counts.get(TaskStatus.PENDING, 0) + counts.get(TaskStatus.ASSIGNED, 0)),
        failed_tasks_24h=failed_24h,
        active_jobs=active_jobs,
        tasks_by_status={str(k): int(v) for k, v in counts.items()},
    )


@router.get("/tasks", response_model=Page[AgentTaskOut])
def list_tasks(
    db: DbSession,
    organization_id: OrgId,
    _: CurrentUser,
    research_job_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    agent_key: str | None = None,
    task_status: TaskStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Page[AgentTaskOut]:
    stmt = select(AgentTask).where(AgentTask.organization_id == organization_id)
    if research_job_id:
        stmt = stmt.where(AgentTask.research_job_id == research_job_id)
    if company_id:
        stmt = stmt.where(AgentTask.company_id == company_id)
    if agent_key:
        stmt = stmt.where(AgentTask.agent_key == agent_key)
    if task_status:
        stmt = stmt.where(AgentTask.status == task_status)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(AgentTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        .scalars()
        .all()
    )
    return Page[AgentTaskOut](
        items=[AgentTaskOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


@router.get("/tasks/{task_id}", response_model=AgentTaskDetail)
def get_task(task_id: uuid.UUID, db: DbSession, organization_id: OrgId, _: CurrentUser) -> AgentTaskDetail:
    task = db.execute(
        select(AgentTask).where(AgentTask.id == task_id, AgentTask.organization_id == organization_id)
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return AgentTaskDetail.model_validate(task)


@router.get("/tasks/{task_id}/executions", response_model=list[AgentExecutionOut])
def task_executions(task_id: uuid.UUID, db: DbSession, _: CurrentUser) -> list[AgentExecutionOut]:
    rows = (
        db.execute(
            select(AgentExecution)
            .where(AgentExecution.task_id == task_id)
            .order_by(AgentExecution.attempt)
        )
        .scalars()
        .all()
    )
    return [AgentExecutionOut.model_validate(r) for r in rows]


@router.get("/logs", response_model=list[AgentLogOut])
def list_logs(
    db: DbSession,
    _: CurrentUser,
    research_job_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    agent_key: str | None = None,
    level: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
) -> list[AgentLogOut]:
    stmt = select(AgentLog)
    if research_job_id:
        stmt = stmt.where(AgentLog.research_job_id == research_job_id)
    if company_id:
        stmt = stmt.where(AgentLog.company_id == company_id)
    if agent_key:
        stmt = stmt.where(AgentLog.agent_key == agent_key)
    if level:
        stmt = stmt.where(AgentLog.level == level)
    rows = db.execute(stmt.order_by(AgentLog.created_at.desc()).limit(limit)).scalars().all()
    return [AgentLogOut.model_validate(r) for r in rows]


@router.get("/messages", response_model=list[AgentMessageOut])
def list_messages(
    db: DbSession,
    _: CurrentUser,
    research_job_id: uuid.UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[AgentMessageOut]:
    stmt = select(AgentMessage)
    if research_job_id:
        stmt = stmt.where(AgentMessage.research_job_id == research_job_id)
    rows = db.execute(stmt.order_by(AgentMessage.created_at.desc()).limit(limit)).scalars().all()
    return [AgentMessageOut.model_validate(r) for r in rows]


@router.get("/{agent_key}", response_model=AgentDetail)
def get_agent(agent_key: str, db: DbSession, _: CurrentUser) -> AgentDetail:
    agent = db.execute(select(Agent).where(Agent.key == agent_key)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentDetail.model_validate(agent)


@router.post("/{agent_key}/toggle", response_model=AgentOut)
def toggle_agent(
    agent_key: str, payload: AgentToggle, admin: RequireAdmin, db: DbSession
) -> AgentOut:
    agent = db.execute(select(Agent).where(Agent.key == agent_key)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    agent.is_enabled = payload.is_enabled
    agent.status = AgentStatus.IDLE if payload.is_enabled else AgentStatus.DISABLED
    audit(db, user=admin, action="agent.toggle", entity_type="agent", entity_id=agent_key,
          detail=str(payload.is_enabled))
    db.commit()
    db.refresh(agent)
    return AgentOut.model_validate(agent)
