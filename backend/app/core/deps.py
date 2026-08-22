"""FastAPI dependencies: authentication, role enforcement and audit helpers."""
from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.enums import UserRole
from app.models.org import AuditLog, User

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]

# Ordered from most to least privileged; a role satisfies any requirement at or below it.
ROLE_RANK: dict[str, int] = {
    UserRole.ADMIN: 40,
    UserRole.RESEARCHER: 30,
    UserRole.SALES_USER: 20,
    UserRole.VIEWER: 10,
}


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials, expected_type="access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(minimum: UserRole) -> Callable[[User], User]:
    """Dependency factory enforcing a minimum role."""

    def dependency(user: CurrentUser) -> User:
        if ROLE_RANK.get(user.role, 0) < ROLE_RANK[minimum]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the {minimum} role or higher.",
            )
        return user

    return dependency


RequireAdmin = Annotated[User, Depends(require_role(UserRole.ADMIN))]
RequireResearcher = Annotated[User, Depends(require_role(UserRole.RESEARCHER))]
RequireSales = Annotated[User, Depends(require_role(UserRole.SALES_USER))]


def org_id(user: CurrentUser) -> uuid.UUID:
    if user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User has no organization"
        )
    return user.organization_id


OrgId = Annotated[uuid.UUID, Depends(org_id)]


def audit(
    db: Session,
    *,
    user: User | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    detail: str | None = None,
    request: Request | None = None,
) -> None:
    db.add(
        AuditLog(
            organization_id=user.organization_id if user else None,
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent", "")[:400] if request else None,
        )
    )
