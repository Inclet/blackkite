"""Sharing a private manual item (spec 6: "An admin can promote one to public
only with the owner's consent").

* opportunity.share_consent_at: when the owner allowed an admin to make the
  item public (NULL = not allowed).
* opportunity.made_public_at / made_public_by: when and by which admin it was
  made public (NULL = never; made_public_by NULL also once that admin's account
  is deleted). A published item keeps owner_user_id for attribution only.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-26 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "opportunity",
        sa.Column("share_consent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "opportunity",
        sa.Column("made_public_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("opportunity", sa.Column("made_public_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_opportunity_made_public_by_user"),
        "opportunity",
        "user",
        ["made_public_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_opportunity_made_public_by"), "opportunity", ["made_public_by"]
    )
    op.create_check_constraint(
        op.f("ck_opportunity_made_public_is_public"),
        "opportunity",
        "made_public_at IS NULL OR visibility = 'public'",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_opportunity_made_public_is_public"), "opportunity", type_="check"
    )
    op.drop_index(op.f("ix_opportunity_made_public_by"), table_name="opportunity")
    op.drop_constraint(
        op.f("fk_opportunity_made_public_by_user"), "opportunity", type_="foreignkey"
    )
    op.drop_column("opportunity", "made_public_by")
    op.drop_column("opportunity", "made_public_at")
    op.drop_column("opportunity", "share_consent_at")
