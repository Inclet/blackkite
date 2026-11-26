"""Trigram (pg_trgm) support for linking procurement records to tenders.

Migration 0020 runs ``CREATE EXTENSION IF NOT EXISTS pg_trgm`` and adds:

* GIN trigram indexes (``gin_trgm_ops``) on ``award.entity_key``, ``award.title``,
  ``procurement_plan_item.entity_key`` and ``procurement_plan_item.description_key``;
* a btree expression index on the initials of ``entity_key`` (no extension
  needed), for acronym matches ("RTDA" for "Rwanda Transport Development Agency").

pg_trgm ships with PostgreSQL (contrib) and is a trusted extension: a database
user with CREATE on the database can install it without being a superuser. If
the migration cannot create it, it logs a warning and skips the trigram indexes;
``pipeline/records.link_tender`` then checks every unlinked record as before
(``available``), only slower. Install it later with
``CREATE EXTENSION pg_trgm`` as a privileged user and re-run migration 0020
(``alembic downgrade 0019 && alembic upgrade head``).

The indexes live in the migration only, not in the models, so ``alembic check``
agrees whether or not the extension is there (``migrations/env.py`` skips them).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

TRGM_INDEXES = {
    "award": {"ix_award_entity_key_trgm": "entity_key", "ix_award_title_trgm": "title"},
    "procurement_plan_item": {
        "ix_procurement_plan_item_entity_key_trgm": "entity_key",
        "ix_procurement_plan_item_description_key_trgm": "description_key",
    },
}
INITIALS_INDEXES = {
    "award": "ix_award_entity_initials",
    "procurement_plan_item": "ix_procurement_plan_item_entity_initials",
}
MIGRATION_ONLY_INDEXES = frozenset(
    {n for t in TRGM_INDEXES.values() for n in t} | set(INITIALS_INDEXES.values())
)

# ``dedupe._initials`` in SQL, on a key that is already normalised (single
# spaces between words): drop the skip words, keep each word's first character.
# Kept as literal SQL (no bound parameters) so it matches the index expression.
_SKIP = "of|and|the|for|in|de|du|des|la|le"


def initials_sql(column: str) -> str:
    stripped = f"regexp_replace(' ' || {column} || ' ', ' (({_SKIP}) )+', ' ', 'g')"
    return f"btrim(regexp_replace({stripped}, ' +([^ ])[^ ]*', '\\1', 'g'))"


_CACHE_KEY = "blackkite.trgm_available"


def available(session: Session) -> bool:
    """pg_trgm is installed in this database (cached on the session)."""
    if _CACHE_KEY not in session.info:
        session.info[_CACHE_KEY] = bool(
            session.scalar(
                sa.text("SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'")
            )
        )
    return session.info[_CACHE_KEY]
