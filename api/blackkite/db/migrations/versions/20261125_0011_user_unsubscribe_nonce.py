"""user.unsubscribe_nonce: the per-user part of every signed unsubscribe link
(decision 43). Existing users get a random value; rotating it revokes old links.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-25 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NONCE_SQL = "replace(gen_random_uuid()::text, '-', '')"


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "unsubscribe_nonce",
            sa.String(32),
            nullable=False,
            server_default=sa.text(NONCE_SQL),
        ),
    )


def downgrade() -> None:
    op.drop_column("user", "unsubscribe_nonce")
