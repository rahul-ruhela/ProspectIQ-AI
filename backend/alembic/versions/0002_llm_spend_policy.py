"""Add the LLM spend policy table.

Paid model usage is gated on a ceiling the operator sets at runtime from the UI, so
the policy belongs in the database rather than the environment.

Revision ID: 0002_spend_policy
Revises: 0001_initial
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_spend_policy"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "llm_spend_policy"


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE):
        # 0001 runs `Base.metadata.create_all`, so a database created after this
        # model was added already has the table.
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("allow_paid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("daily_limit_usd", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("monthly_limit_usd", sa.Float(), nullable=False, server_default="20.0"),
        sa.Column("alert_threshold_pct", sa.Float(), nullable=False, server_default="80.0"),
        # TimestampMixin populates these with server_default rather than in Python,
        # so the column definitions must carry it or every insert fails on NULL.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
