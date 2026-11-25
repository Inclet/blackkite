"""profile.backfill_attempts: a failing backfill backs off and is given up after
a configured number of attempts; a new request resets the count.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-25 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profile",
        sa.Column(
            "backfill_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("profile", "backfill_attempts")
