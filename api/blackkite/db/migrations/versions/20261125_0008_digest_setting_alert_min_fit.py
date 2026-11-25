"""digest_setting.alert_min_fit replaces alert_threshold (spec 8, spec 12: alerts
are chosen by fit word, never by the numeric score).

Existing thresholds map to the nearest word: 75 or more -> strong, 60 or more ->
good, anything lower (or NULL) -> NULL (alerts off). The downgrade maps back
strong -> 75, good -> 60.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-25 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "digest_setting",
        sa.Column("alert_min_fit", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_digest_setting_alert_min_fit"),
        "digest_setting",
        "alert_min_fit IN ('strong', 'good')",
    )
    op.execute(
        """UPDATE digest_setting SET alert_min_fit = CASE
             WHEN alert_threshold >= 75 THEN 'strong'
             WHEN alert_threshold >= 60 THEN 'good'
           END"""
    )
    op.drop_constraint(
        op.f("ck_digest_setting_alert_threshold_range"),
        "digest_setting",
        type_="check",
    )
    op.drop_column("digest_setting", "alert_threshold")


def downgrade() -> None:
    op.add_column(
        "digest_setting",
        sa.Column("alert_threshold", sa.SmallInteger(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_digest_setting_alert_threshold_range"),
        "digest_setting",
        "alert_threshold IS NULL OR alert_threshold BETWEEN 0 AND 100",
    )
    op.execute(
        """UPDATE digest_setting SET alert_threshold = CASE alert_min_fit
             WHEN 'strong' THEN 75
             WHEN 'good' THEN 60
           END"""
    )
    op.drop_constraint(
        op.f("ck_digest_setting_alert_min_fit"), "digest_setting", type_="check"
    )
    op.drop_column("digest_setting", "alert_min_fit")
