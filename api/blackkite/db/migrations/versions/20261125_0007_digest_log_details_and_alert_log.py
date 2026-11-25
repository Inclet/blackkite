"""digest_log: digest_date (one weekly digest per user per Kigali day) and details
(what each item looked like when sent); alert_log: one urgent alert per item.

Existing digest_log rows take digest_date from sent_at (Kigali day). No digest has
been sent before this revision, so no user has two rows on one day.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-25 12:33:11.713477
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KIGALI_TODAY = "((now() AT TIME ZONE 'Africa/Kigali')::date)"


def upgrade() -> None:
    op.create_table(
        "alert_log",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunity.id"],
            name=op.f("fk_alert_log_opportunity_id_opportunity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_alert_log_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_log")),
        sa.UniqueConstraint(
            "user_id",
            "opportunity_id",
            name=op.f("uq_alert_log_user_id_opportunity_id"),
        ),
    )
    op.create_index(
        op.f("ix_alert_log_opportunity_id"), "alert_log", ["opportunity_id"]
    )
    op.create_index(op.f("ix_alert_log_user_id"), "alert_log", ["user_id"])

    op.add_column(
        "digest_log",
        sa.Column(
            "digest_date",
            sa.Date(),
            server_default=sa.text(KIGALI_TODAY),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE digest_log SET digest_date = (sent_at AT TIME ZONE 'Africa/Kigali')::date"
    )
    op.add_column(
        "digest_log",
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        op.f("uq_digest_log_user_id_digest_date"),
        "digest_log",
        ["user_id", "digest_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_digest_log_user_id_digest_date"), "digest_log", type_="unique"
    )
    op.drop_column("digest_log", "details")
    op.drop_column("digest_log", "digest_date")
    op.drop_index(op.f("ix_alert_log_user_id"), table_name="alert_log")
    op.drop_index(op.f("ix_alert_log_opportunity_id"), table_name="alert_log")
    op.drop_table("alert_log")
