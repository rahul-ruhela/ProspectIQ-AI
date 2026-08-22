"""Registration, login, refresh and profile endpoints."""
from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, RequireAdmin, audit
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.enums import UserRole
from app.models.org import Organization, User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    PasswordChange,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.schemas.common import Message

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "org"


def _tokens(user: User) -> TokenPair:
    claims = {"role": str(user.role), "org": str(user.organization_id) if user.organization_id else None}
    return TokenPair(
        access_token=create_access_token(str(user.id), **claims),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbSession, request: Request) -> AuthResponse:
    """Create an organization and its first user. That user becomes the admin."""
    existing = db.execute(select(User).where(User.email == payload.email.lower())).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    base_slug = _slugify(payload.organization_name)
    slug = base_slug
    suffix = 1
    while db.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none():
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    organization = Organization(name=payload.organization_name, slug=slug)
    db.add(organization)
    db.flush()

    user = User(
        organization_id=organization.id,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.ADMIN,
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    audit(db, user=user, action="auth.register", entity_type="user", entity_id=str(user.id), request=request)
    db.commit()
    db.refresh(user)
    return AuthResponse(user=UserOut.model_validate(user), tokens=_tokens(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: DbSession, request: Request) -> AuthResponse:
    user = db.execute(select(User).where(User.email == payload.email.lower())).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        # Identical message for both cases so the endpoint cannot enumerate accounts.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    user.last_login_at = datetime.now(UTC)
    audit(db, user=user, action="auth.login", entity_type="user", entity_id=str(user.id), request=request)
    db.commit()
    db.refresh(user)
    return AuthResponse(user=UserOut.model_validate(user), tokens=_tokens(user))


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    claims = decode_token(payload.refresh_token, expected_type="refresh")
    if claims is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = db.execute(select(User).where(User.id == claims["sub"])).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active")
    return _tokens(user)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/change-password", response_model=Message)
def change_password(payload: PasswordChange, user: CurrentUser, db: DbSession) -> Message:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    audit(db, user=user, action="auth.change_password", entity_type="user", entity_id=str(user.id))
    db.commit()
    return Message(detail="Password updated")


# --- user administration -------------------------------------------------------

users_router = APIRouter(prefix="/users", tags=["Users"])


@users_router.get("", response_model=list[UserOut])
def list_users(admin: RequireAdmin, db: DbSession) -> list[UserOut]:
    rows = (
        db.execute(
            select(User)
            .where(User.organization_id == admin.organization_id)
            .order_by(User.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [UserOut.model_validate(row) for row in rows]


@users_router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, admin: RequireAdmin, db: DbSession) -> UserOut:
    if db.execute(select(User).where(User.email == payload.email.lower())).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        organization_id=admin.organization_id,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    audit(db, user=admin, action="user.create", entity_type="user", detail=payload.email)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@users_router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: str, payload: UserUpdate, admin: RequireAdmin, db: DbSession) -> UserOut:
    user = db.execute(
        select(User).where(User.id == user_id, User.organization_id == admin.organization_id)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id and payload.role is not None and payload.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own admin role"
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    audit(db, user=admin, action="user.update", entity_type="user", entity_id=str(user.id))
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@users_router.get("/count", response_model=dict)
def user_count(admin: RequireAdmin, db: DbSession) -> dict:
    total = db.execute(
        select(func.count(User.id)).where(User.organization_id == admin.organization_id)
    ).scalar_one()
    return {"total": total}
