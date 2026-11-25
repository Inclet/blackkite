"""Migrations: upgrade head -> downgrade base -> upgrade head on an empty DB, no drift."""

import pytest
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
            return bool(
                c.scalar(
                    sa.text("SELECT count(*) FROM pg_extension WHERE extname='vector'")
                )
            )
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
        "user",
        "invite",
        "profile",
        "digest_setting",
        "source",
        "source_run",
        "source_suggestion",
        "user_source_mute",
        "opportunity",
        "opportunity_source",
        "document",
        "change_event",
        "award",
        "user_opportunity",
        "digest_log",
        "user_opportunity_score",  # decision 19: scores per profile, state per user
        "session",
        "login_token",
        "http_cache",  # conditional GET cache for collectors (not per user)
        "alert_log",  # urgent alerts sent, one per (user, opportunity)
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
    _exec(
        url, "INSERT INTO \"user\" (email) VALUES ('a@example.com'), ('b@example.com')"
    )
    _exec(
        url,
        """INSERT INTO digest_setting (user_id, channel, address, frequency, day)
                  SELECT id, 'email', email, 'weekly', CASE WHEN email LIKE 'a%' THEN 'fri' END
                  FROM "user" """,
    )
    command.upgrade(cfg, "0002")
    assert _exec(url, "SELECT DISTINCT frequency, day FROM digest_setting") == [
        ("weekly", "mon")
    ]
    _exec(
        url,
        "UPDATE digest_setting SET frequency = 'off' WHERE address = 'b@example.com'",
    )
    command.downgrade(cfg, "0001")
    assert _exec(url, "SELECT address FROM digest_setting") == [("a@example.com",)]


def test_0003_splits_state_from_scores_and_back(make_database):
    url = make_database("bk_migr")
    cfg = alembic_config(url)
    command.upgrade(cfg, "0002")
    _exec(url, "INSERT INTO \"user\" (email) VALUES ('a@example.com')")
    _exec(
        url,
        """INSERT INTO profile (user_id, name, type)
                  SELECT id, n, 'business' FROM "user", unnest(ARRAY['p1', 'p2']) n""",
    )
    _exec(url, "INSERT INTO opportunity (stream, title) VALUES ('tender', 't')")
    # Two profiles scored the same opportunity; the earlier row was saved, the later
    # dismissed. Saved is further along, so it wins over the more recent dismissal.
    _exec(
        url,
        """INSERT INTO user_opportunity
                    (user_id, opportunity_id, profile_id, score, state, note, updated_at)
                  SELECT u.id, o.id, p.id,
                         CASE p.name WHEN 'p1' THEN 80 ELSE 40 END,
                         CASE p.name WHEN 'p1' THEN 'saved' ELSE 'dismissed' END,
                         CASE p.name WHEN 'p1' THEN 'call them' ELSE 'too small' END,
                         CASE p.name WHEN 'p1' THEN now() - interval '1 day' ELSE now() END
                  FROM "user" u, opportunity o, profile p""",
    )
    command.upgrade(cfg, "0003")
    assert _exec(url, "SELECT state, note FROM user_opportunity") == [
        ("saved", "call them\n\ntoo small")
    ]
    assert _exec(
        url,
        """SELECT p.name, s.score FROM user_opportunity_score s
                         JOIN profile p ON p.id = s.profile_id ORDER BY p.name""",
    ) == [("p1", 80), ("p2", 40)]
    command.downgrade(cfg, "0002")
    assert _exec(
        url,
        """SELECT p.name, uo.score, uo.state FROM user_opportunity uo
                         JOIN profile p ON p.id = uo.profile_id ORDER BY p.name""",
    ) == [("p1", 80, "saved"), ("p2", 40, "saved")]


def test_0003_keeps_most_progressed_state_and_orders_notes(make_database):
    url = make_database("bk_migr")
    cfg = alembic_config(url)
    command.upgrade(cfg, "0002")
    _exec(url, "INSERT INTO \"user\" (email) VALUES ('a@example.com')")
    _exec(
        url,
        """INSERT INTO profile (user_id, name, type)
                  SELECT id, n, 'business' FROM "user",
                         unnest(ARRAY['p1', 'p2', 'p3', 'p4', 'p5', 'p6']) n""",
    )
    _exec(
        url,
        "INSERT INTO opportunity (stream, title) VALUES ('tender', 'a'), ('tender', 'b')",
    )
    # (opportunity, profile, state, dismiss_reason, note, age in days)
    rows = [
        # a: acting (old) beats saved, dismissed and a fresh unseen; the duplicate note
        # appears once, at its earliest position; notes run oldest first, not A-Z.
        ("a", "p1", "acting", None, "zebra first", 5),
        ("a", "p2", "saved", None, "apple second", 3),
        ("a", "p3", "dismissed", "too small", "zebra first", 2),
        ("a", "p4", "unseen", None, None, 0),
        # b: done beats acting; among equals the latest wins.
        ("b", "p1", "acting", None, None, 1),
        ("b", "p2", "done", None, "older done", 4),
        ("b", "p3", "done", None, "newer done", 2),
        ("b", "p5", "dismissed", "not ours", None, 0),
        ("b", "p6", "unseen", None, None, 0),
    ]
    for opp, prof, state, reason, note, age in rows:
        _exec(
            url,
            """INSERT INTO user_opportunity
                        (user_id, opportunity_id, profile_id, state, dismiss_reason, note,
                         updated_at)
                      SELECT u.id, o.id, p.id, :state, :reason, :note,
                             now() - make_interval(days => :age)
                      FROM "user" u, opportunity o, profile p
                      WHERE o.title = :opp AND p.name = :prof""",
            opp=opp,
            prof=prof,
            state=state,
            reason=reason,
            note=note,
            age=age,
        )
    command.upgrade(cfg, "0003")
    got = _exec(
        url,
        """SELECT o.title, uo.state, uo.dismiss_reason, uo.note
                        FROM user_opportunity uo JOIN opportunity o ON o.id = uo.opportunity_id
                        ORDER BY o.title""",
    )
    assert got == [
        ("a", "acting", None, "zebra first\n\napple second"),
        ("b", "done", None, "older done\n\nnewer done"),
    ]
    # b's kept row is the newer of the two done rows (2 days old, not 4).
    assert _exec(
        url,
        """SELECT round(extract(epoch FROM now() - uo.updated_at) / 86400)
                         FROM user_opportunity uo JOIN opportunity o ON o.id = uo.opportunity_id
                         WHERE o.title = 'b'""",
    ) == [(2,)]
    assert _exec(url, "SELECT count(*) FROM user_opportunity_score") == [(9,)]
    command.downgrade(cfg, "0002")
    command.upgrade(cfg, "head")


def test_0005_raises_sub_second_rate_limits_to_one(make_database):
    url = make_database("bk_migr")
    cfg = alembic_config(url)
    command.upgrade(cfg, "0004")
    _exec(
        url,
        """INSERT INTO source (name, home_url, streams, kind, collector_type, rate_limit)
           VALUES ('fast', 'https://a.example.org', '{tender}', 'original', 'rss', 0.2),
                  ('one', 'https://b.example.org', '{tender}', 'original', 'rss', 1),
                  ('slow', 'https://c.example.org', '{tender}', 'original', 'rss', 7.5),
                  ('unset', 'https://d.example.org', '{tender}', 'original', 'rss', NULL)""",
    )
    command.upgrade(cfg, "0005")
    rows = _exec(url, "SELECT name, rate_limit FROM source ORDER BY name")
    assert rows == [("fast", 1.0), ("one", 1.0), ("slow", 7.5), ("unset", None)]
    with pytest.raises(sa.exc.IntegrityError):
        _exec(url, "UPDATE source SET rate_limit = 0.5 WHERE name = 'slow'")

    # The downgrade restores the old check only; raised values stay at 1.
    command.downgrade(cfg, "0004")
    rows = _exec(url, "SELECT name, rate_limit FROM source ORDER BY name")
    assert rows == [("fast", 1.0), ("one", 1.0), ("slow", 7.5), ("unset", None)]
    _exec(url, "UPDATE source SET rate_limit = 0.5 WHERE name = 'slow'")
    command.upgrade(cfg, "head")


def test_0007_digest_date_from_sent_at_and_unique(make_database):
    url = make_database("bk_migr")
    cfg = alembic_config(url)
    command.upgrade(cfg, "0006")
    _exec(url, "INSERT INTO \"user\" (email) VALUES ('a@example.com')")
    # 23:30 UTC on 29 Nov is 01:30 on Monday 30 Nov in Kigali.
    _exec(
        url,
        """INSERT INTO digest_log (user_id, sent_at)
           SELECT id, '2026-11-29 23:30:00+00' FROM "user" """,
    )
    command.upgrade(cfg, "0007")
    assert _exec(url, "SELECT digest_date::text, details::text FROM digest_log") == [
        ("2026-11-30", "{}")
    ]
    with pytest.raises(sa.exc.IntegrityError):
        _exec(
            url,
            """INSERT INTO digest_log (user_id, digest_date)
               SELECT id, '2026-11-30' FROM "user" """,
        )
    command.downgrade(cfg, "0006")
    assert _exec(url, "SELECT count(*) FROM digest_log") == [(1,)]


def test_0008_maps_alert_threshold_to_fit_word_and_back(make_database):
    url = make_database("bk_migr")
    cfg = alembic_config(url)
    command.upgrade(cfg, "0007")
    for i, t in enumerate(["90", "75", "74", "60", "59", "0", "NULL"]):
        _exec(url, f"INSERT INTO \"user\" (email) VALUES ('u{i}@example.com')")
        _exec(
            url,
            f"""INSERT INTO digest_setting (user_id, channel, address, alert_threshold)
                SELECT id, 'email', email, {t} FROM "user"
                WHERE email = 'u{i}@example.com'""",
        )
    command.upgrade(cfg, "0008")
    rows = _exec(
        url,
        "SELECT address, alert_min_fit FROM digest_setting ORDER BY address",
    )
    assert rows == [
        ("u0@example.com", "strong"),
        ("u1@example.com", "strong"),
        ("u2@example.com", "good"),
        ("u3@example.com", "good"),
        ("u4@example.com", None),
        ("u5@example.com", None),
        ("u6@example.com", None),
    ]
    with pytest.raises(sa.exc.IntegrityError):
        _exec(url, "UPDATE digest_setting SET alert_min_fit = 'possible'")
    command.downgrade(cfg, "0007")
    rows = _exec(
        url, "SELECT address, alert_threshold FROM digest_setting ORDER BY address"
    )
    assert [t for _, t in rows] == [75, 75, 60, 60, None, None, None]
    command.upgrade(cfg, "head")
