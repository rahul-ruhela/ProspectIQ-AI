"""Reusable model primitives: UUID identity, timestamps and data provenance."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import VerificationStatus


# JSONB on PostgreSQL, plain JSON elsewhere (keeps the test suite runnable on SQLite).
JSONBType = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProvenanceMixin:
    """Attached to every table that stores a claim about the outside world.

    The platform's core rule is that no value exists without a traceable origin.
    A row that cannot answer "where did this come from" must be stored with
    ``verification_status = UNKNOWN`` rather than guessed.
    """

    source: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        String(32), default=VerificationStatus.NEEDS_VERIFICATION, nullable=False
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def provenance(self) -> dict:
        return {
            "source": self.source,
            "source_url": self.source_url,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
            "last_verified_at": self.last_verified_at,
        }
