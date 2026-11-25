"""profile.backfill_requested_at and profile.scored_version: profile backfills
(spec 5) move off the request path to the worker. user_opportunity_score.
profile_hash: model judgements are reused while the profile's scoring-relevant
content is unchanged, not while its updated_at is (a rename no longer counts).

Existing profiles were backfilled in the request that saved them, so they start
up to date: scored_version = version, nothing pending.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-25 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profile",
        sa.Column("backfill_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("profile", sa.Column("scored_version", sa.Integer(), nullable=True))
    op.execute("UPDATE profile SET scored_version = version, updated_at = updated_at")
    op.add_column(
        "user_opportunity_score",
        sa.Column("profile_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_profile_backfill_requested_at",
        "profile",
        ["backfill_requested_at"],
        postgresql_where=sa.text("backfill_requested_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_profile_backfill_requested_at", table_name="profile")
    op.drop_column("user_opportunity_score", "profile_hash")
    op.drop_column("profile", "scored_version")
    op.drop_column("profile", "backfill_requested_at")
