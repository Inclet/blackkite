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
        "user_opportunity_score",  # decision 19: scores per profile, state per user
        "session", "login_token",
    }
    assert spec == set(Base.metadata.tables)


def _exec(url: str, sql: str, **params):
    eng = sa.create_engine(url)
    try:
        with eng.begin() as c:
            r = c.execute(sa.text(sql), params)
            return r.all() if r.returns_rows else None
    finally:
        eng.dispose()


def test_0002_moves_digest_days_to_monday_and_downgrade_drops_off(make_database):
    url = make_database("bk_migr")
    cfg = alembic_config(url)
    command.upgrade(cfg, "0001")
    _exec(url, "INSERT INTO \"user\" (email) VALUES ('a@example.com'), ('b@example.com')")
    _exec(url, """INSERT INTO digest_setting (user_id, channel, address, frequency, day)
                  SELECT id, 'email', email, 'weekly', CASE WHEN email LIKE 'a%' THEN 'fri' END
                  FROM "user" """)
    command.upgrade(cfg, "0002")
    assert _exec(url, "SELECT DISTINCT frequency, day FROM digest_setting") == [("weekly", "mon")]
    _exec(url, "UPDATE digest_setting SET frequency = 'off' WHERE address = 'b@example.com'")
    command.downgrade(cfg, "0001")
    assert _exec(url, "SELECT address FROM digest_setting") == [("a@example.com",)]


def test_0003_splits_state_from_scores_and_back(make_database):
    url = make_database("bk_migr")
    cfg = alembic_config(url)
    command.upgrade(cfg, "0002")
    _exec(url, "INSERT INTO \"user\" (email) VALUES ('a@example.com')")
    _exec(url, """INSERT INTO profile (user_id, name, type)
                  SELECT id, n, 'business' FROM "user", unnest(ARRAY['p1', 'p2']) n""")
    _exec(url, "INSERT INTO opportunity (stream, title) VALUES ('tender', 't')")
    # Two profiles scored the same opportunity; the later row was dismissed.
    _exec(url, """INSERT INTO user_opportunity
                    (user_id, opportunity_id, profile_id, score, state, note, updated_at)
                  SELECT u.id, o.id, p.id,
                         CASE p.name WHEN 'p1' THEN 80 ELSE 40 END,
                         CASE p.name WHEN 'p1' THEN 'saved' ELSE 'dismissed' END,
                         CASE p.name WHEN 'p1' THEN 'call them' ELSE 'too small' END,
                         CASE p.name WHEN 'p1' THEN now() - interval '1 day' ELSE now() END
                  FROM "user" u, opportunity o, profile p""")
    command.upgrade(cfg, "0003")
    assert _exec(url, "SELECT state, note FROM user_opportunity") == [
        ("dismissed", "call them\n\ntoo small")
    ]
    assert _exec(url, """SELECT p.name, s.score FROM user_opportunity_score s
                         JOIN profile p ON p.id = s.profile_id ORDER BY p.name""") == [
        ("p1", 80), ("p2", 40)
    ]
    command.downgrade(cfg, "0002")
    assert _exec(url, """SELECT p.name, uo.score, uo.state FROM user_opportunity uo
                         JOIN profile p ON p.id = uo.profile_id ORDER BY p.name""") == [
        ("p1", 80, "dismissed"), ("p2", 40, "dismissed")
    ]
