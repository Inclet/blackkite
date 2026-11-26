"""source_run.warnings: what a run skipped without failing (decision 49), e.g.
emails with no usable link (sender, subject, date). Existing runs get [].

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-26 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_run",
        sa.Column(
            "warnings",
            JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("source_run", "warnings")
