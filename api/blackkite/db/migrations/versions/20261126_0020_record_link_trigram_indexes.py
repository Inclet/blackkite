"""Trigram and initials indexes for linking awards and plan items to tenders
(M5 perf).

* ``CREATE EXTENSION IF NOT EXISTS pg_trgm``. pg_trgm is a trusted contrib
  extension: the database user needs CREATE on the database (no superuser). If
  it cannot be created, a warning is logged and the trigram indexes are skipped;
  linking then falls back to checking every unlinked record (blackkite/db/trgm.py).
  When this migration created the extension it marks it with a comment, and only
  then does the downgrade drop it.
* GIN ``gin_trgm_ops`` indexes on award.entity_key, award.title,
  procurement_plan_item.entity_key and procurement_plan_item.description_key.
* A btree index on the initials of entity_key, both tables (acronym matches).

The SQL here is frozen; blackkite/db/trgm.py builds the same initials expression
for queries.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-26 22:00:00
"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")

MARK = "installed by blackkite migration 0020"
TRGM = {
    "award": {"ix_award_entity_key_trgm": "entity_key", "ix_award_title_trgm": "title"},
    "procurement_plan_item": {
        "ix_procurement_plan_item_entity_key_trgm": "entity_key",
        "ix_procurement_plan_item_description_key_trgm": "description_key",
    },
}
INITIALS = {
    "award": "ix_award_entity_initials",
    "procurement_plan_item": "ix_procurement_plan_item_entity_initials",
}
INITIALS_SQL = (
    "btrim(regexp_replace(regexp_replace(' ' || entity_key || ' ', "
    "' ((of|and|the|for|in|de|du|des|la|le) )+', ' ', 'g'), "
    "' +([^ ])[^ ]*', '\\1', 'g'))"
)


def _has_trgm(bind) -> bool:
    return bool(
        bind.scalar(
            sa.text("SELECT count(*) FROM pg_extension WHERE extname='pg_trgm'")
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    had = _has_trgm(bind)
    if not had:
        try:
            with bind.begin_nested():
                bind.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                bind.exec_driver_sql(f"COMMENT ON EXTENSION pg_trgm IS '{MARK}'")
        except sa.exc.DBAPIError as e:
            log.warning(
                "pg_trgm could not be created (%s); trigram indexes skipped. "
                "Record linking still works, checking every unlinked record. "
                "Install it as a user with CREATE on the database, then run "
                "`alembic downgrade 0019 && alembic upgrade head`.",
                str(e.orig).strip() if e.orig else e,
            )
    for table, name in INITIALS.items():
        op.execute(f"CREATE INDEX {name} ON {table} (({INITIALS_SQL}))")
    if _has_trgm(bind):
        for table, indexes in TRGM.items():
            for name, column in indexes.items():
                op.execute(
                    f"CREATE INDEX {name} ON {table} USING gin ({column} gin_trgm_ops)"
                )


def downgrade() -> None:
    for indexes in TRGM.values():
        for name in indexes:
            op.execute(f"DROP INDEX IF EXISTS {name}")
    for name in INITIALS.values():
        op.execute(f"DROP INDEX IF EXISTS {name}")
    bind = op.get_bind()
    comment = bind.scalar(
        sa.text(
            "SELECT obj_description(oid, 'pg_extension') FROM pg_extension "
            "WHERE extname = 'pg_trgm'"
        )
    )
    if comment == MARK:
        op.execute("DROP EXTENSION IF EXISTS pg_trgm")
