"""Migrations: upgrade head -> downgrade base -> upgrade head on an empty DB, no drift."""

import sqlalchemy as sa
from alembic import command

from blackkite.db.base import Base
from tests.conftest import alembic_config


def _tables(url: str) -> set[str]:
    eng = sa.create_engine(url)
    try:
        return set(sa.inspect(eng).get_table_names()) - {"alembic_version"}
    finally:
        eng.dispose()


def _has_vector(url: str) -> bool:
    eng = sa.create_engine(url)
    try:
        with eng.connect() as c:
            return bool(c.scalar(sa.text("SELECT count(*) FROM pg_extension WHERE extname='vector'")))
    finally:
        eng.dispose()


def test_round_trip_and_no_drift(make_database):
    url = make_database("bk_migr")
    cfg = alembic_config(url)
    expected = set(Base.metadata.tables)

    command.upgrade(cfg, "head")
    assert _tables(url) == expected
    assert _has_vector(url)
    command.check(cfg)  # raises if models and migrations disagree

    command.downgrade(cfg, "base")
    assert _tables(url) == set()
    assert not _has_vector(url)

    command.upgrade(cfg, "head")
    assert _tables(url) == expected
    command.check(cfg)


def test_schema_has_every_spec_table():
    spec = {
        "user", "invite", "profile", "digest_setting", "source", "source_run",
        "source_suggestion", "user_source_mute", "opportunity", "opportunity_source",
        "document", "change_event", "award", "user_opportunity", "digest_log",
        "session", "login_token",
    }
    assert spec == set(Base.metadata.tables)
