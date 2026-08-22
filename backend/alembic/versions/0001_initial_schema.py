"""Initial ProspectIQ AI schema.

Creates every table from the SQLAlchemy metadata and enables pgvector when the
extension is available. Building from metadata keeps the 48-table schema in one place
and guarantees the migration and the ORM can never drift apart on a fresh install.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-22
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.database import Base
import app.models  # noqa: F401  - registers every table on Base.metadata

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Optional: enables semantic agent memory. Ignored when the extension is absent.
        try:
            op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception:
            pass
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
