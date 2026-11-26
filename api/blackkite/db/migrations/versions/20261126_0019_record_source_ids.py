"""Awards and plan items keep every source that listed them (M5 fix list 8).

* award.source_ids, procurement_plan_item.source_ids: uuid[] of every source that
  has listed the record (``source_id`` stays the first). Visibility reads the
  list, so retiring the first source does not hide a record another active
  source still lists. Existing rows get ``[source_id]``. GIN-indexed.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-26 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("award", "procurement_plan_item")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "source_ids",
                postgresql.ARRAY(sa.Uuid()),
                nullable=False,
                server_default=sa.text("'{}'::uuid[]"),
            ),
        )
        op.execute(
            f"UPDATE {table} SET source_ids = ARRAY[source_id] "
            "WHERE source_id IS NOT NULL"
        )
        op.create_index(
            f"ix_{table}_source_ids", table, ["source_ids"], postgresql_using="gin"
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f"ix_{table}_source_ids", table_name=table)
        op.drop_column(table, "source_ids")
