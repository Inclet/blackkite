"""Private manual items (spec 6): opportunity.manual_url, the link the owner
gave (no source carries a manual item), and opportunity.score_requested_at,
the queue the worker scores items from (a created or edited private item, for
its owner only; a published one, for everyone). NULL = nothing pending.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-26 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("opportunity", sa.Column("manual_url", sa.Text(), nullable=True))
    op.add_column(
        "opportunity",
        sa.Column("score_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_opportunity_score_requested_at",
        "opportunity",
        ["score_requested_at"],
        postgresql_where=sa.text("score_requested_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_opportunity_score_requested_at", table_name="opportunity")
    op.drop_column("opportunity", "score_requested_at")
    op.drop_column("opportunity", "manual_url")
