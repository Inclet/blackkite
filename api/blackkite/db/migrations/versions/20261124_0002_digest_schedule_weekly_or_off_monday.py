"""Digest schedule: weekly on Monday, or off (decision 18).

frequency allows weekly | off (default weekly); day is Monday only in v1 and
defaults to it. Existing rows move to Monday.

Downgrade is lossy for rows set to `off`: the old schema cannot say "off", and
mapping them to weekly would start mail the user stopped, so those rows are
deleted (no digest_setting row means no digest).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24 15:37:48.854599
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_DAYS = "'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'"


def upgrade() -> None:
    op.drop_constraint(op.f('ck_digest_setting_frequency'), 'digest_setting', type_='check')
    op.create_check_constraint(
        op.f('ck_digest_setting_frequency'), 'digest_setting', "frequency IN ('weekly', 'off')"
    )
    op.alter_column('digest_setting', 'frequency', existing_type=sa.VARCHAR(length=32),
                    server_default='weekly')

    op.drop_constraint(op.f('ck_digest_setting_day'), 'digest_setting', type_='check')
    op.execute("UPDATE digest_setting SET day = 'mon' WHERE day IS DISTINCT FROM 'mon'")
    op.create_check_constraint(op.f('ck_digest_setting_day'), 'digest_setting', "day IN ('mon')")
    op.alter_column('digest_setting', 'day', existing_type=sa.VARCHAR(length=32),
                    nullable=False, server_default='mon')


def downgrade() -> None:
    op.alter_column('digest_setting', 'day', existing_type=sa.VARCHAR(length=32),
                    nullable=True, server_default=None)
    op.drop_constraint(op.f('ck_digest_setting_day'), 'digest_setting', type_='check')
    op.create_check_constraint(op.f('ck_digest_setting_day'), 'digest_setting', f"day IN ({OLD_DAYS})")

    op.execute("DELETE FROM digest_setting WHERE frequency = 'off'")
    op.alter_column('digest_setting', 'frequency', existing_type=sa.VARCHAR(length=32),
                    server_default=None)
    op.drop_constraint(op.f('ck_digest_setting_frequency'), 'digest_setting', type_='check')
    op.create_check_constraint(
        op.f('ck_digest_setting_frequency'), 'digest_setting', "frequency IN ('weekly')"
    )
