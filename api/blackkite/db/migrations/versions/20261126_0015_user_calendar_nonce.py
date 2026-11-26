"""user.calendar_nonce: the per-user part of the signed calendar feed link
(docs/api-contract.md section 5), separate from the unsubscribe nonce so each
can be revoked alone. Existing users get a random value.
user.calendar_nonce_rotated_at: when the user last revoked their feed link
(NULL = never).

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-26 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NONCE_SQL = "replace(gen_random_uuid()::text, '-', '')"


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "calendar_nonce",
            sa.String(32),
            nullable=False,
            server_default=sa.text(NONCE_SQL),
        ),
    )
    op.add_column(
        "user",
        sa.Column(
            "calendar_nonce_rotated_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("user", "calendar_nonce_rotated_at")
    op.drop_column("user", "calendar_nonce")
