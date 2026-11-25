"""source_status_change: a source's status history for the admin source screen
(spec 4.4). Existing sources get no back-filled rows; history starts now.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-25 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = ("suggested", "testing", "active", "paused", "retired")


def _status(name: str) -> sa.Enum:
    return sa.Enum(
        *STATUSES, name=name, native_enum=False, create_constraint=True, length=32
    )


def upgrade() -> None:
    op.create_table(
        "source_status_change",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("old_status", _status("old_status"), nullable=True),
        sa.Column("new_status", _status("new_status"), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["user.id"],
            name=op.f("fk_source_status_change_changed_by_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source.id"],
            name=op.f("fk_source_status_change_source_id_source"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_status_change")),
    )
    op.create_index(
        op.f("ix_source_status_change_changed_by"),
        "source_status_change",
        ["changed_by"],
    )
    op.create_index(
        "ix_source_status_change_source_id_at",
        "source_status_change",
        ["source_id", "at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_status_change_source_id_at", table_name="source_status_change"
    )
    op.drop_index(
        op.f("ix_source_status_change_changed_by"), table_name="source_status_change"
    )
    op.drop_table("source_status_change")
