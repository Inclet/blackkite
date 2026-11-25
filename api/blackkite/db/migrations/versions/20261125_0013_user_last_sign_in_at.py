"""user.last_sign_in_at: when the user last started a session, for the admin
users screen. Existing users take their newest session's start, if any.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-25 22:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("last_sign_in_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """UPDATE "user" u SET last_sign_in_at = s.at
           FROM (SELECT user_id, max(created_at) AS at FROM session GROUP BY user_id) s
           WHERE s.user_id = u.id"""
    )


def downgrade() -> None:
    op.drop_column("user", "last_sign_in_at")
