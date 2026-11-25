"""source_run.items_failed: items the pipeline rolled back in a run.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-25 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_run",
        sa.Column("items_failed", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("source_run", "items_failed")
