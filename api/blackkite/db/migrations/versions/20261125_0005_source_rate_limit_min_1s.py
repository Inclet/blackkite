"""source.rate_limit: at least 1 second between requests to one host.

Existing values under 1 s are raised to 1 s before the check is added.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-25 12:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE source SET rate_limit = 1 WHERE rate_limit < 1")
    op.drop_constraint(op.f("ck_source_rate_limit_positive"), "source", type_="check")
    op.create_check_constraint(
        op.f("ck_source_rate_limit_min_1s"),
        "source",
        "rate_limit IS NULL OR rate_limit >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_source_rate_limit_min_1s"), "source", type_="check")
    op.create_check_constraint(
        op.f("ck_source_rate_limit_positive"),
        "source",
        "rate_limit IS NULL OR rate_limit > 0",
    )
