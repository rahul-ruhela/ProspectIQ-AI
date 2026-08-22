"""Shared response envelopes and provenance schema."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import VerificationStatus

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Provenance(BaseModel):
    """Attached to every outward-facing fact."""

    source: str | None = None
    source_url: str | None = None
    confidence: float = 0.0
    verification_status: VerificationStatus = VerificationStatus.NEEDS_VERIFICATION
    last_verified_at: datetime | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class Message(BaseModel):
    detail: str


class IdResponse(BaseModel):
    id: uuid.UUID
